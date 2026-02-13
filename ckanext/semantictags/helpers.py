import requests

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

from ckan.common import config
from ckan.plugins.toolkit import asbool
from ckan.lib.munge import munge_tag
from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery

API_URL = 'https://api.terminology.tib.eu/api/v2/ontologies/{onto}/classes'
ONTOLOGIES_KEY = 'ckanext.semantictags.ontologies'
FREE_TAGS_KEY = 'ckanext.semantictags.allow_free_tags'
FORCE_RELOAD_KEY = 'ckanext.semantictags.force_reload'


def get_terms_by_ontology(onto):
    api_url = API_URL.format(onto=onto)
    terms = []
    page = 0
    while True:
        params = {'page': page, 'size': 50}
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()

        for term in data.get('elements', []):
            iri = term.get('iri')
            label = term.get('label')[0]
            if isinstance(label, dict):
                label = label.get('value')

            if iri and label:
                terms.append({'iri': iri, 'label': label, 'ontology': onto})

        total_pages = data.get('totalPages')
        if total_pages is not None:
            page += 1
            if page >= total_pages:
                break
        else:
            if not data.get('elements'):
                break
            page += 1

    return terms


def resolve_vocab_tags(data_dict):
    tags = data_dict.get('tags')
    tag_string = data_dict.get('tag_string')
    if not tags and tag_string:
        raw = [t.strip() for t in tag_string.split(',') if t.strip()]
        tags = [{'name': t} for t in raw]
    if not tags:
        return

    vocab_name = config.get('ldm_tags.vocabulary_name', 'oeo')
    vocab = VocabularyQuery.read_name(vocab_name)
    if not vocab:
        return

    resolved = []
    for tag in tags:
        if isinstance(tag, str):
            tag = {'name': tag}
        name = tag.get('name')
        if not name:
            continue
        munged = munge_tag(name)
        tag = dict(tag)
        tag['name'] = munged
        vocab_tag = TagQuery.read_name(munged, vocabulary_id=vocab.id)
        if vocab_tag:
            tag['id'] = vocab_tag.id
            tag['vocabulary_id'] = vocab.id
        resolved.append(tag)

    if resolved:
        data_dict['tags'] = resolved
        if tag_string is not None:
            data_dict.pop('tag_string', None)


def generate_tag_vocabulary(ontologies=None):
    tags_util = LDM_tags_util()
    tags_util.create_vocabulary(ontologies=ontologies)


class LDM_tags_util():

    def __init__(self):
        log.debug('Inside the Tag Plugin')

        self.vocabulary_name_default = config.get('ldm_tags.vocabulary_name', "oeo")

        ontologies_config = config.get(ONTOLOGIES_KEY, 'oeo')
        self.ontologies = ontologies_config.split()
        log.debug(f"ONTOLOGIES LIST: {self.ontologies}")

    def _check_vocabulary_name(self, vocabulary_name):
        if not vocabulary_name:
            vocabulary_name = self.vocabulary_name_default
        return vocabulary_name

    def create_vocabulary(self, vocabulary_name="", ontologies=None):
        log.debug('in create_vocabulary')
        vocabulary_name = self._check_vocabulary_name(vocabulary_name)
        force_reload_vocabulary_tags = asbool(config.get(FORCE_RELOAD_KEY))
        log.debug(f'Force reloading vocabulary {force_reload_vocabulary_tags}')

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

        if not to_delete and not to_add and not force_reload_vocabulary_tags:
            log.debug("All ontologies are already loaded.")
            return

        # Delete ontologies that are no longer needed
        for ontology in to_delete:
            OntologyManager.delete_ontology(vocab.id, ontology)

        # Force reload
        if force_reload_vocabulary_tags:
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
