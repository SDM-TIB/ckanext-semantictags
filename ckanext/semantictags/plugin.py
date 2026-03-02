import logging

import ckan.lib.base as base
import ckan.logic as logic
import ckan.model as model
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import requests as http_requests
from ckan.common import config
from ckan.logic.action.create import package_create as core_package_create
from ckan.logic.action.get import package_show as core_package_show
from ckan.logic.action.update import package_update as core_package_update
from ckan.plugins.toolkit import asbool
from flask import Blueprint, request

from ckanext.semantictags import cli
from ckanext.semantictags.helpers import ONTOLOGIES_KEY, FREE_TAGS_KEY, FORCE_RELOAD_KEY, generate_tag_vocabulary, \
    LDM_tags_util, resolve_vocab_tags
from ckanext.semantictags.model import tag as tag_model
from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery

NotFound = logic.NotFound

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

TIB_TS_API = 'https://api.terminology.tib.eu/api/v2'


@toolkit.side_effect_free
def term_details(context, data_dict):
    """
    Fetch term details from TIB Terminology Service (OLS4 v2) by IRI.

    :param iri: the term IRI
    :type iri: str

    :returns: dict with label, iri, ontology_name, ontology_title, definition
    """
    iri = data_dict.get('iri', '').strip()
    if not iri:
        raise toolkit.ValidationError({'iri': ['Missing value']})

    try:
        term_resp = http_requests.get(
            f'{TIB_TS_API}/entities',
            params={'iri': iri, 'size': 1},
            timeout=5
        )
        term_resp.raise_for_status()
        term_data = term_resp.json()

        elements = term_data.get('elements', [])
        if not elements:
            return {'error': 'Term not found'}

        term = elements[0]
        ontology_id = term.get('ontologyId', '')

        description = term.get('definition') or []
        definition = description[0] if description else None

        return {
            'label': term.get('label'),
            'iri': term.get('iri'),
            'curie': term.get('curie'),
            'ontology_name': ontology_id,
            'definition': definition,
        }

    except http_requests.RequestException as e:
        log.warning(f'TIB TS request failed for IRI {iri}: {e}')
        return {'error': 'Terminology service unavailable'}


@toolkit.side_effect_free
def autocomplete_term(context, data_dict):
    """
    Autocomplete tags from ontologies.

    :param q: partial query string (preferred)
    :type q: str
    :param incomplete: partial query string (fallback)
    :type incomplete: str
    :param limit: maximum number of results (default 10)
    :type limit: int

    :returns: list of tag labels/names, e.g. ["Tag 1", "Tag 2", "..."]
    """
    query = data_dict.get('q') or data_dict.get('incomplete', '')
    limit = int(data_dict.get('limit') or 10)

    tags_util = LDM_tags_util()
    vocab = VocabularyQuery.read_name(tags_util.vocabulary_name_default)
    if not vocab:
        return []

    res = OntologyManager.search_terms(query, limit=limit, vocabulary_id=vocab.id)

    results = []
    for t in res:
        label = getattr(t, 'label', None) or t.name
        ontology = getattr(t, 'ontology', '') or ''
        results.append({'id': label, 'text': label, 'ontology': ontology})
    return results

@toolkit.side_effect_free
def suggest_tags_from_text(context, data_dict):
    """
    Suggest tags from description text using NFDI4Energy Annotator API.
    """
    text = data_dict.get('text', '').strip()
    if not text:
        raise toolkit.ValidationError({'text': ['Missing or empty text']})

    # determine which ontologies to query (either passed or configured)
    tags_util = LDM_tags_util()
    ontology_ids = data_dict.get('ontology_ids') or tags_util.ontologies
    if not ontology_ids:
        raise toolkit.ValidationError({'ontology_ids': ['No ontologies configured']})

    try:
        annotator_response = http_requests.post(
            'https://service.tib.eu/sandbox/nfdi4energyannotator/annotate',
            json={
                'text': text,
                'ontology_ids': ontology_ids,
                'max_depth': 0
            },
            timeout=30
        )
        annotator_response.raise_for_status()
        data = annotator_response.json()

        matches = data.get('matches', [])

        # only keep matches from the requested ontologies and dedupe by iri
        ontology_set = set(ontology_ids)
        seen_iris = {}
        for match in matches:
            iri = match.get('iri')
            ontology = (match.get('ontologyId') or '').lower()
            if iri and ontology in ontology_set:
                if iri not in seen_iris or match.get('score', 0) > seen_iris[iri]['score']:
                    seen_iris[iri] = match

        # build the result list using same field names as term_details
        suggested_tags = []
        for match in seen_iris.values():
            suggested_tags.append({
                'label': match.get('label', match.get('token', '')),
                'iri': match.get('iri'),
                'curie': match.get('curie'),
                'ontology_name': match.get('ontologyId'),
            })

        return {'suggestions': suggested_tags, 'count': len(suggested_tags)}

    except http_requests.RequestException as e:
        log.error(f'Annotator request failed: {e}')
        return {'error': 'Annotation service unavailable', 'suggestions': []}


@toolkit.side_effect_free
def package_show(context, data_dict):
    data = core_package_show(context, data_dict)
    tags = data.get('tags', [])
    if not tags:
        return data

    for tag in tags:
        tag_id = tag.get('id')
        tag_row = TagQuery.read(tag_id)
        if not tag_row:
            log.debug(f"Tag {tag.get('name')} not found in Tag Table")
            continue
        tag['iri'] = tag_row.iri
        tag['ontology'] = tag_row.ontology
        if hasattr(tag_row, 'label') and tag_row.label:
            tag['display_name'] = tag_row.label
        if getattr(tag_row, 'vocabulary_id', None) and not tag.get('vocabulary_id'):
            tag['vocabulary_id'] = tag_row.vocabulary_id

    return data


def package_create(context, data_dict):
    resolve_vocab_tags(data_dict)
    return core_package_create(context, data_dict)


def package_update(context, data_dict):
    resolve_vocab_tags(data_dict)
    return core_package_update(context, data_dict)


def get_data_module_source():
    return '/api/3/action/semantictags_autocomplete?incomplete=?'


def get_available_ontologies():
    return OntologyManager.list_ontologies()


def free_tags_allowed():
    return config.get(FREE_TAGS_KEY)

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


class LDMtagsPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IActions) 
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IPackageController, inherit=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tag_model.init_table()
        # generate_tag_vocabulary()

    def before_create(self, context, data_dict):
        resolve_vocab_tags(data_dict)
        return data_dict

    def before_update(self, context, data_dict):
        resolve_vocab_tags(data_dict)
        return data_dict

    def get_commands(self):
        return cli.get_commands()

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_resource('static', 'semantictags')
        toolkit.add_ckan_admin_tab(config_, 'semantictags.admin', 'SemanticTags', icon='tags')

    def update_config_schema(self, schema):
        ignore_missing = toolkit.get_validator('ignore_missing')

        schema.update({
            ONTOLOGIES_KEY: [ignore_missing],
            FREE_TAGS_KEY: [ignore_missing],
            FORCE_RELOAD_KEY: [ignore_missing]
        })

        return schema

    def get_helpers(self):
        """Register SemanticTags template helpers."""
        # Template helper function names should begin with the name of the
        # extension they belong to, to avoid clashing with functions from
        # other extensions.
        return {
            'semantictags_data_module_source': get_data_module_source,
            'semantictags_available_ontologies': get_available_ontologies,
            'semantictags_enable_freetags': free_tags_allowed
        }

    def get_actions(self):
        return {
            'semantictags_autocomplete': autocomplete_term,
            'semantictags_term_details': term_details,
            'semantictags_suggest_tags': suggest_tags_from_text,
            'package_show': package_show, 
            'package_create': package_create,
            'package_update': package_update
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
                elif action == 'free_tags':
                    free_tags = request.form.get(FREE_TAGS_KEY)
                    try:
                        free_tags = asbool(free_tags)
                    except (ValueError, TypeError):
                        toolkit.h.flash_error(toolkit._('Please specify a value that can be parsed as a boolean.'))
                    logic.get_action(u'config_option_update')({
                        u'user': toolkit.c.user
                    }, {
                        FREE_TAGS_KEY: 'true' if free_tags else 'false'
                    })
                    toolkit.h.flash_success(toolkit._('Free tags option updated successfully.'))
                elif action == 'force_reload':
                    force_reload = request.form.get(FORCE_RELOAD_KEY)
                    try:
                        force_reload = asbool(force_reload)
                    except (ValueError, TypeError):
                        toolkit.h.flash_error(toolkit._('Please specify a value that can be parsed as a boolean.'))
                    logic.get_action(u'config_option_update')({
                        u'user': toolkit.c.user
                    }, {
                        FORCE_RELOAD_KEY: 'true' if force_reload else 'false'
                    })
                    toolkit.h.flash_success(toolkit._('Force reload option updated successfully.'))

            return toolkit.render('admin_semantictags.jinja2',
                                  extra_vars={
                                      'ontologies': config.get(ONTOLOGIES_KEY, '').strip(),
                                      'free_tags': config.get(FREE_TAGS_KEY).lower(),
                                      'force_reload': config.get(FORCE_RELOAD_KEY).lower()
                                  })

        return blueprint
