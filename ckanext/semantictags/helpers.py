import os
import logging
import requests
from datetime import datetime
from ckan.common import config
from ckan.lib.munge import munge_tag
from ckan.plugins.toolkit import asbool
from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery

import redis

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

API_URL = 'https://api.terminology.tib.eu/api/v2/ontologies/'
ONTOLOGIES_KEY = 'ckanext.semantictags.ontologies'
FREE_TAGS_KEY = 'ckanext.semantictags.allow_free_tags'
FORCE_RELOAD_KEY = 'ckanext.semantictags.force_reload'

redis_url = os.getenv('CKAN_REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis.from_url(redis_url)
UPDATE_FREQUENCY_KEY = 'ckanext.semantictags.updatefrequency'
COOLDOWN_KEY = 'ckanext.semantictags.cooldown'

def search_ontologies(query, limit=10):
    available = get_available_ontologies()
    if not query: 
        return {'results': available[:limit]}

    query = query.lower()
    results = []
    for onto in available: 
        if query in onto['text'].lower():
            results.append(onto)

        if len(results) >= limit: 
            break
    
    return {'results': results}

def get_available_ontologies(page_size = 100):
    
    ontologies = []
    page = 0
    
    try: 
        while True: 
            response = requests.get(API_URL, params={'page': page, 'size': page_size},
                timeout=15)
            response.raise_for_status()
            data = response.json()

            for element in data.get('elements', []):
                ontology_id = element.get('ontologyId')
                title = element.get('title')
                ontologies.append({
                    'id': ontology_id, 
                    'text': f'{title} ({ontology_id})'})
                
            total_pages = data.get('totalPages', 1)
            page += 1
            if page >= total_pages:
                break
    except Exception as e:
        log.error(f'Failed to fetch ontology list from TIB TS: {e}')
        return []
    
    return ontologies

def get_terms_by_ontology(onto):
    api_url = f"{API_URL}{onto}/classes"
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

    tags_util = LDM_tags_util()
    vocab = VocabularyQuery.read_name(tags_util.vocabulary_name_default)
    if not vocab:
        return

    resolved = []
    for tag in tags:
        if isinstance(tag, str):
            tag = {'name': tag}
        name = tag.get('name') or tag.get('display_name') or tag.get('label') or tag.get('value')
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


class LDM_tags_util:
    def __init__(self):
        log.debug('Inside the Tag Plugin')

        self.vocabulary_name_default = config.get('ldm_tags.vocabulary_name', "semantictags")

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
        if force_reload_vocabulary_tags:
            to_add = requested_ontologies
        else:
            to_add = requested_ontologies - existing_ontologies

        log.debug(f"Existing: {existing_ontologies}, Requested: {requested_ontologies}")
        log.debug(f"To delete: {to_delete}, To add: {to_add}")

        if not to_delete and not to_add and not force_reload_vocabulary_tags:
            log.debug("All ontologies are already loaded.")
            return

        # Delete ontologies that are no longer needed
        for ontology in to_delete:
            OntologyManager.delete_ontology(vocab.id, ontology)
            clear_last_loaded(ontology)

        for ontology in to_add:
            # check again if loading is required
            if not force_reload_vocabulary_tags and OntologyManager.is_ontology_loaded(vocab.id, ontology):
                log.debug(f"Ontology {ontology} was loaded by another worker, skipping")
                continue

            log.debug(f"Loading ontology: {ontology}")
            try:
                terms = get_terms_by_ontology(ontology)
                OntologyManager.add_ontology(vocab.id, ontology, terms, refresh_existing=force_reload_vocabulary_tags)
                log.debug(f"Loaded {len(terms)} terms from {ontology}")

                set_last_loaded(ontology)
            except Exception as e:
                log.error(f"Failed to load ontology {ontology}: {e}")


def reload_single_ontology(ontology_id, refresh_existing=True): 

    tags_util = LDM_tags_util()
    vocab = VocabularyQuery.read_name(tags_util.vocabulary_name_default)

    if vocab is None:
        log.error(f'reload_single_ontology: vocabulary "{tags_util.vocabulary_name_default}" does not exist.')
        raise RuntimeError(f'Vocabulary not found, cannot reload "{ontology_id}".')
 
    terms = get_terms_by_ontology(ontology_id)
    OntologyManager.add_ontology(vocab.id, ontology_id, terms, refresh_existing=refresh_existing)
    
    set_last_loaded(ontology_id)
    log.info(f'reload_single_ontology: "{ontology_id}" updated, last_loaded timestamp set.')

def store_value(key, value):
    try:
        redis_client.set(key, value)
        log.debug(f"Stored in Redis: {key} -> {value}")
    except Exception as e:
        log.error(f"Error storing value in Redis: {e}")

def get_value(key, default_value=None):
    try:
        value = redis_client.get(key)
        if value is not None:
            value = value.decode('utf-8')
            log.debug(f"Retrieved from Redis: {key} -> {value}")
            return value
        return default_value
    except Exception as e:
        log.error(f"Error retrieving value from Redis: {e}")
        return default_value
    
def acquire_lock(lock_name):
    lock = redis_client.lock(lock_name, timeout=30)
    acquired = lock.acquire(blocking=False)
    return acquired, lock   

def set_cooldown(ttl_seconds):
    try:
        if ttl_seconds > 0:
            redis_client.set(COOLDOWN_KEY, '1', ex=ttl_seconds)
    except Exception as e:
        log.error(f"Error setting cooldown in Redis: {e}")

 
def clear_cooldown():
    try:
        redis_client.delete(COOLDOWN_KEY)
    except Exception as e:
        log.error(f"Error clearing cooldown in Redis: {e}")

def is_cooling_down():
    try:
        return redis_client.exists(COOLDOWN_KEY) > 0
    except Exception as e:
        log.error(f"Error checking cooldown in Redis: {e}")
        return False
    

def _last_loaded_key(ontology_id: str) -> str:
    return f'ckanext.semantictags.last_loaded:{ontology_id}'

def get_last_loaded(ontology_id): 
    ts = get_value(_last_loaded_key(ontology_id))
    if ts is None: 
        return None
    try: 
        return datetime.fromisoformat(ts)
    except ValueError:
        return None

def set_last_loaded(ontology_id):
    store_value(_last_loaded_key(ontology_id), datetime.utcnow().isoformat())

def clear_last_loaded(ontology_id):
    try:
        redis_client.delete(_last_loaded_key(ontology_id))
    except Exception as e:
        log.error(f"Error clearing last_loaded for {ontology_id}: {e}")