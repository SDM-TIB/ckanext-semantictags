import requests
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from flask import Blueprint, request
from ckan.common import config
d = toolkit.g

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import ckan.lib.base as base
import ckan.logic as logic
import ckan.model as model

NotFound = logic.NotFound

from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery
from ckanext.semantictags.model import tag as tag_model


# HELPERS
# *******
API_URL = 'https://service.tib.eu/ts4tib/api/ontologies/{onto}/terms?size=50'
ONTOLOGIES_KEY = 'ckanext.semantictags.ontologies'


# TODO: test using more than one ontology


@toolkit.side_effect_free
def autocomplete_term(context, data_dict):
    """
    Autocomplete tags from ontologies.

    :param q: partial query string
    :type q: str
    :param limit: maximum number of results (default 10)
    :type limit: int
    :param ontology: name of the ontology to check (by default all are considered)
    :type ontology: str

    :returns: JSON in the same format as CKAN util autocomplete:
              ["Tag 1", "Tag 2", "...", "Tag n"]
    """
    query = data_dict.get('q') or data_dict.get('incomplete', '')
    ontology = data_dict.get('ontology')
    limit = int(data_dict.get('limit') or 10)

    res = OntologyManager.search_terms(query, ontology, limit)
    return [t.name for t in res]


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


def get_data_module_source():
    return '/api/3/action/semantictags_autocomplete?incomplete=?'


def get_available_ontologies():
    return OntologyManager.list_ontologies()


def _check_access():
    context = {
        'model': model,
        'session': model.Session,
        'user': toolkit.c.user,
        'auth_user_obj': toolkit.c.userobj
    }
    try:
        logic.check_access('sysadmin', context, {})
    except logic.NotAuthorized:
        base.abort(403, toolkit._('Need to be system administrator to administer.'))


# *******
class LDM_tags_util():

    def __init__(self):
        log.debug('Inside the Tag Plugin')

        self.vocabulary_name_default = config.get('ldm_tags.vocabulary_name', "oeo")

        ontologies_config = config.get(ONTOLOGIES_KEY, 'oeo')
        self.ontologies = ontologies_config.split()
        log.debug(f"ONTOLOGIES LIST: {self.ontologies}")

        # Use the following option to delete the vocabulary and recreate it again
        self.force_reload_vocabulary_tags = config.get('ckanext.semantictags.force_reload_vocabulary_tags', True)
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

    def _check_vocabulary_name(self, vocabulary_name):
        if not vocabulary_name:
            vocabulary_name = self.vocabulary_name_default
        return vocabulary_name

    def create_vocabulary(self, vocabulary_name="", ontologies=None):
        log.debug('in create_vocabulary')
        vocabulary_name = self._check_vocabulary_name(vocabulary_name)
        
        if ontologies is None:
            ontologies = self.ontologies

        vocab = VocabularyQuery.read_name(vocabulary_name)
        if not vocab:
            vocab = VocabularyQuery.create(vocabulary_name)

        # check which ontologies already exist in DB
        existing_ontologies = OntologyManager.get_loaded_ontologies(vocab.id)
        requested_ontologies = set(ontologies)
        
        to_delete = existing_ontologies - requested_ontologies
        to_add = requested_ontologies - existing_ontologies
        
        log.debug(f"Existing: {existing_ontologies}, Requested: {requested_ontologies}")
        log.debug(f"To delete: {to_delete}, To add: {to_add}")

        if not to_delete and not to_add and not self.force_reload_vocabulary_tags:
            log.debug("All ontologies are already loaded.")
            return
        
        # Delete ontologies that are no longer needed
        for ontology in to_delete:
            OntologyManager.delete_ontology(vocab.id, ontology)

        # Force reload 
        if self.force_reload_vocabulary_tags:
            to_reload = existing_ontologies & requested_ontologies  
            for ontology in to_reload:
                OntologyManager.delete_ontology(vocab.id, ontology)
            to_add = to_add | to_reload 

        for ontology in to_add:
            # check again if loading is required 
            if OntologyManager.is_ontology_loaded(vocab.id, ontology):
                log.debug(f"Ontology {ontology} was loaded by another worker, skipping")
                continue

            log.debug(f"Loading ontology: {ontology}")
            try:
                terms = get_terms_by_ontology(ontology)
                OntologyManager.add_ontology(vocab.id, ontology, terms)
                log.debug(f"Loaded {len(terms)} terms from {ontology}")
            except Exception as e:
                log.error(f"Failed to load ontology {ontology}: {e}")


def generate_tag_vocabulary(ontologies=None):
    tags_util = LDM_tags_util()
    tags_util.create_vocabulary(ontologies=ontologies)


class LDMtagsPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IActions) 
    plugins.implements(plugins.IBlueprint)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tag_model.init_table()
        generate_tag_vocabulary()

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_ckan_admin_tab(config_, 'semantictags.admin', 'SemanticTags', icon='tags')
        # generate vocabulary if necessary
        generate_tag_vocabulary()

    def update_config_schema(self, schema):
        ignore_missing = toolkit.get_validator('ignore_missing')

        schema.update({
            ONTOLOGIES_KEY: [ignore_missing]
        })

        return schema

    def get_helpers(self):
        """Register the most_popular_groups() function above as a template
        helper function.
        """
        # Template helper function names should begin with the name of the
        # extension they belong to, to avoid clashing with functions from
        # other extensions.
        return {'semantictags_data_module_source': get_data_module_source,
                'semantictags_available_ontologies': get_available_ontologies}

    def get_actions(self):
        return {
            'semantictags_autocomplete': autocomplete_term
        }

    def get_blueprint(self):
        blueprint = Blueprint('semantictags', __name__)

        @blueprint.route('/ckan-admin/semantictags', methods=['GET', 'POST'])
        def admin():
            _check_access()

            if request.method == 'POST':
                action = request.form.get('action', None)
                if action == 'ontologies':
                    ontologies = request.form.get(ONTOLOGIES_KEY, '').strip()
                    if not ontologies:
                        toolkit.h.flash_error(toolkit._('Please specify at least one ontology.'))
                    else:
                        logic.get_action(u'config_option_update')({
                            u'user': toolkit.c.user
                        }, {
                            ONTOLOGIES_KEY: ontologies
                        })

                        # Update ontology list
                        ontologies_list = ontologies.split()
                        generate_tag_vocabulary(ontologies=ontologies_list)

                        toolkit.h.flash_success(toolkit._('New ontologies set successfully.'))

            return toolkit.render('admin_semantictags.jinja2',
                                  extra_vars={
                                      'ontologies': config.get(ONTOLOGIES_KEY, '').strip()
                                  })

        return blueprint
