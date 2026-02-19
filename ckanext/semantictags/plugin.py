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
from ckan.logic.action.create import package_create as core_package_create
from ckan.logic.action.update import package_update as core_package_update
from ckan.logic.action.get import package_show as core_package_show

NotFound = logic.NotFound

from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery
from ckanext.semantictags.model import tag as tag_model
from ckan.plugins.toolkit import asbool
from ckanext.semantictags import cli
from ckanext.semantictags.helpers import API_URL, ONTOLOGIES_KEY, FREE_TAGS_KEY, FORCE_RELOAD_KEY, get_terms_by_ontology, generate_tag_vocabulary, LDM_tags_util, resolve_vocab_tags


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
    limit = int(data_dict.get('limit') or 10)

    tags_util = LDM_tags_util()
    vocab = VocabularyQuery.read_name(tags_util.vocabulary_name_default)
    if not vocab:
        return []

    res = OntologyManager.search_terms(query, limit=limit, vocabulary_id=vocab.id)

    # Return label if available, otherwise fall back to name
    return [getattr(t, 'label', None) or t.name for t in res]


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tag_model.init_table()
        # generate_tag_vocabulary()

    def get_commands(self):
        return cli.get_commands()

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
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
        """Register the most_popular_groups() function above as a template
        helper function.
        """
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
