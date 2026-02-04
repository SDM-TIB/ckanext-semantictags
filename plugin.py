import requests
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from flask import Blueprint, jsonify, request
from ckan.common import config
d = toolkit.g

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import os
import yaml
import ckan.logic as logic
import ckan.model as model
NotFound = logic.NotFound

from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery
from ckanext.semantictags.model import tag as tag_model


# HELPERS
# *******
API_URL = 'https://service.tib.eu/ts4tib/api/ontologies/{onto}/terms?size=50'



# TODO
# - add database table for the terms, iri, and ontology (example: https://github.com/SDM-TIB/LDM_Docker/blob/main/Plugins/ckanext-doi/ckanext/doi/model/doi.py)
# - populate the database with entries from the Terminology Service with a given ontology, here 'oeo'
# - display close matches (see https://github.com/ckan/ckan/blob/2.9/ckan/logic/action/get.py#L2209-L2212)
#   - maybe we will add a new API call for our purpose
# - allow more than just one ontology


@toolkit.side_effect_free
def autocomplete_term(context, data):
    '''
    Docstring for autocomplete_term
    
    :param data: Description
    '''
    query = data.get('q') or data.get('incomplete', '')
    ontology = data.get('ontology')
    limit = data.get('limit', 10)

    res = OntologyManager.search_terms(query, ontology, limit)
    return [
        {'name': t.name, 'iri': getattr(t, 'iri', None)}
        for t in res
    ]

def get_terms_by_ontology(onto):
    api_url = API_URL.format(onto=onto)
    terms = []
    while True:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()

        for term in data['_embedded']['terms']:
            iri = term.get('iri')
            label = term.get('label')

            if iri and label:
                terms.append({'iri': iri, 'label': label, 'ontology': onto})

        if data['_links'].get('next') is not None:
            api_url = data['_links']['next']['href']
        else:
            break

    return terms

def get_tag_vocabulary_name():
    tags_util = LDM_tags_util()
    name = tags_util.vocabulary_name_default
    return name

def get_ckan_data_module_source():
    tags_util = LDM_tags_util()
    dsource = tags_util.get_ckan_data_module_source()
    return dsource

def get_available_ontologies():
    return OntologyManager.list_ontologies()

def load_ontology(ontology_name):
    terms = get_terms_by_ontology(ontology_name)
    OntologyManager.add_ontology(ontology_name, terms)

# *******
class LDM_tags_util():

    def __init__(self):
        log.debug('Inside the Tag Plugin')

        # self.LDMtags_vocabulary_plugin_enabled = toolkit.asbool(config.get('ldm_tags.vocabulary_plugin_enabled', False))
        self.LDMtags_vocabulary_plugin_enabled = True

        # TODO: edit config file (ldm_tags.ontologies = oeo ... ...)
        self.vocabulary_name_default = config.get('ldm_tags.vocabulary_name', "oeo")

        ontologies_config = config.get('ldm_tags.ontologies', 'oeo')
        self.ontologies = ontologies_config.split()

        # Use the following option to delete the vocabulary and recreate it again
        self.force_reload_vocabulary_tags = config.get('ldm_tags.force_reload_vocabulary_tags', True)
        # CKAN's API Actions
        self.action_vocabulary_show = toolkit.get_action('vocabulary_show')
        self.action_vocabulary_create = toolkit.get_action('vocabulary_create')
        self.action_vocabulary_update = toolkit.get_action('vocabulary_update')
        self.action_vocabulary_delete = toolkit.get_action('vocabulary_delete')

        self.action_tag_create = toolkit.get_action('tag_create')
        self.action_tag_delete = toolkit.get_action('tag_delete')
        self.action_tag_list = toolkit.get_action('tag_list')
        # Allow unauthorized execution
        toolkit.auth_allow_anonymous_access(self.action_vocabulary_show)
        toolkit.auth_allow_anonymous_access(self.action_vocabulary_create)
        toolkit.auth_allow_anonymous_access(self.action_vocabulary_update)
        toolkit.auth_allow_anonymous_access(self.action_vocabulary_delete)
        toolkit.auth_allow_anonymous_access(self.action_tag_create)
        toolkit.auth_allow_anonymous_access(self.action_tag_delete)
        toolkit.auth_allow_anonymous_access(self.action_tag_list)

    def get_ckan_data_module_source(self):
        if self.LDMtags_vocabulary_plugin_enabled:
            data_module_source = '/api/2/util/term_autocomplete?incomplete=?'
        else:
            data_module_source = "/api/2/util/term_autocomplete?incomplete=?"
        return data_module_source

    def _check_vocabulary_name(self, vocabulary_name):
        if not vocabulary_name:
            vocabulary_name = self.vocabulary_name_default
        return vocabulary_name

    def read_vocabulary_from_ckan(self, vocabulary_name=""):
        vocabulary_name = self._check_vocabulary_name(vocabulary_name)
        # Load Tag Vocabulary from DB
        log.debug('LOADING TAG VOCABULARY FROM CKAN: ' + str(vocabulary_name))
        context = {'model': model, 'session': model.Session, 'ignore_auth': True, 'user': 'admin'}
        data = {'id': vocabulary_name}
        try:
            result = self.action_vocabulary_show(context, data)
        except NotFound as e:
            log.error("ERROR LOADING TAG VOCABULARY: " + str(e))
            result = {}
        return result

    def create_vocabulary(self, vocabulary_name="", vocabulary_file=""):
        log.debug('in create_vocabulary')
        vocabulary_name = self._check_vocabulary_name(vocabulary_name)

        vocab = VocabularyQuery.read_name(vocabulary_name)
        if vocab and not self.force_reload_vocabulary_tags:
            return
        if vocab:
            TagQuery.delete_vocabulary(vocab.id)
        else:
            vocab = VocabularyQuery.create(vocabulary_name)

        seen = set()
        for ontology in self.ontologies:
            terms = get_terms_by_ontology(ontology)
            for term in terms:
                label = term.get('label')
                if not label:
                    continue
                name = label.replace(',', '_').replace('/', '_')
                key = term.get('iri') or name
                if not key or key in seen:
                    continue
                seen.add(key)
                if TagQuery.read_name(name, vocabulary_id=vocab.id):
                    continue
                TagQuery.create(
                    name=name,
                    vocabulary_id=vocab.id,
                    iri=term.get('iri'),
                    ontology=term.get('ontology') or ontology
                )


def generate_tag_vocabulary():
    tags_util = LDM_tags_util()
    tags_util.create_vocabulary()


class LDMtagsPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    # Declare that this plugin will implement ITemplateHelpers.
    plugins.implements(plugins.ITemplateHelpers)
    # Declare to use autocomplete feature
    plugins.implements(plugins.IActions) 
    plugins.implements(plugins.IBlueprint)

    # this plugin is using the preset "ldmtags_string_autocomplete" in ckanext.scheming.presets.json
    # This presets is setting the "form_snippet": "ldmtags_autocomplete.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tag_model.init_table()
        generate_tag_vocabulary()

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'tibimport')

        # generate vocabulary if necessary
        generate_tag_vocabulary()

    # IBlueprint

    def get_helpers(self):
        '''Register the most_popular_groups() function above as a template
        helper function.

        '''
        # Template helper function names should begin with the name of the
        # extension they belong to, to avoid clashing with functions from
        # other extensions.
        return {'scheming_LDMtags_get_tag_vocabulary_name': get_tag_vocabulary_name,
                'scheming_LDMtags_get_ckan_data_module_source': get_ckan_data_module_source, 
                'scheming_LDMtags_get_available_ontologies': get_available_ontologies}


    def get_actions(self):
        return {
            'term_autocomplete' : autocomplete_term
        }

    def get_blueprint(self):
        blueprint = Blueprint('semantictags', __name__)

        @blueprint.route('/api/2/util/term_autocomplete')
        def term_autocomplete_api():
            query = request.args.get('q') or request.args.get('incomplete', '')
            ontology = request.args.get('ontology')
            limit = request.args.get('limit', 10, type=int)
            res = OntologyManager.search_terms(query, ontology, limit)
            return jsonify([t.name for t in res])

        return blueprint
