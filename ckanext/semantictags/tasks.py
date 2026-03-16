import requests
import re
from datetime import datetime, timedelta
from logging import getLogger
from urllib.parse import urlparse
from apscheduler.jobstores.base import ConflictingIdError
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from ckan.common import config

from ckanext.semantictags.helpers import (
    acquire_lock,
    set_cooldown,
    clear_cooldown,
    is_cooling_down,
    redis_url,
    ONTOLOGIES_KEY,
    UPDATE_FREQUENCY_KEY,
    get_last_loaded,
    reload_single_ontology
)

API_URL = 'https://api.terminology.tib.eu/api/v2/ontologies/{onto}'
log = getLogger(__name__)

def get_ts_last_loaded(ontology_id): 

    try: 
        url = API_URL.format(onto=ontology_id)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        loaded_ts = data.get('loaded')

        if loaded_ts is None:
            log.warning(f'No "loaded" field in TS response for "{ontology_id}".')
            return None
        
        loaded_ts = re.sub(r'(\.\d{6})\d+', r'\1', loaded_ts)
        loaded_ts = re.sub(r'([+-])(\d{2})(\d{2})$', r'\1\2:\3', loaded_ts)
        dt = datetime.fromisoformat(loaded_ts)
        if dt.tzinfo is not None:
            dt = datetime(*dt.utctimetuple()[:6])

        return dt
    
    except requests.RequestException as e:
        log.warning(f'Could not fetch TS metadata for "{ontology_id}": {e}')
        return None

def check_ontology_updates(force=False):
    if not force and is_cooling_down():
        log.debug('check_ontology_updates: Task execution skipped, cooldown is still active.')
        return 
    
    acquired, lock = acquire_lock('semantictags_update_lock')

    if acquired:
        start_time = datetime.utcnow() 
        try:

            ontologies = config.get(ONTOLOGIES_KEY, '').strip()
            if not ontologies: 
                return 
        
            for ontology_id in ontologies.split():
                try:
                    check_ontology(ontology_id, force=force)
                except Exception as e:
                    log.exception(f'Error processing ontology "{ontology_id}": {e}')

        except Exception as e:
            log.exception(f'check_ontology_updates: unexpected error: {e}')
        finally:    
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            interval_seconds = int(config.get(UPDATE_FREQUENCY_KEY, 60)) * 60
            cooldown_ttl = int(0.9 * interval_seconds - elapsed)
            log.debug(f'check_ontology_updates: done in {elapsed:.1f}s, cooldown set to {cooldown_ttl}s.')

            if cooldown_ttl > 0:
                set_cooldown(cooldown_ttl)

            lock.release()
            log.debug('check_ontology_updates: lock released.')
        
    else:
        log.debug('Task execution skipped, another worker holds the lock.')

def check_ontology(ontology_id, force):
    loaded_ts = get_ts_last_loaded(ontology_id)

    if loaded_ts is None: 
        log.warning(f'Could not get TS timestamp for "{ontology_id}", skipping.')
        return
    
    loaded_ldm = get_last_loaded(ontology_id)

    if loaded_ldm is None: 
        log.info(f'"{ontology_id}" has never been loaded, loading now.')
        reload_single_ontology(ontology_id, refresh_existing=True)

    elif force or loaded_ts > loaded_ldm:
        # Terminology service has newer version -> reload

        log.info(
        f'"{ontology_id}" has a newer version on TS '
        f'(TS loaded={loaded_ts.isoformat()}, '
        f'LDM last load={loaded_ldm.isoformat()}), reloading.'
        )
            
        reload_single_ontology(ontology_id, refresh_existing=True)

    else: 
        log.debug(
            f'"{ontology_id}" is up to date '
            f'(TS loaded={loaded_ts.isoformat()}, '
            f'LDM last load={loaded_ldm.isoformat()}), skipping.'
        )
 
class Scheduler:
    instance = None

    class __Scheduler:
        job_id = 'ckanext.semantictags:check_ontology_updates'

        def __init__(self):
            redis_url_parsed = urlparse(redis_url)

            self.scheduler = BackgroundScheduler(
                jobstores={
                    'default': RedisJobStore(
                        jobs_key='apscheduler.semantictags.jobs',
                        run_times_key='apscheduler.semantictags.run_times',
                        host=redis_url_parsed.hostname,
                        port=redis_url_parsed.port,
                        db=int(redis_url_parsed.path.replace('/', ''))
                    )
                },
                job_defaults={
                    'coalesce': True,
                    'max_instances': 1,
                    'misfire_grace_time': None
                },
                timezone='UTC')

            self.scheduler.start(paused=True)
            try:
                interval = int(config.get(UPDATE_FREQUENCY_KEY))
                self.scheduler.add_job(check_ontology_updates, 'interval', minutes=interval, next_run_time=datetime.utcnow() + timedelta(minutes=1), id=self.job_id)
            except ConflictingIdError:
                pass
            self.scheduler.resume()

        def update_interval(self):
            interval = int(config.get(UPDATE_FREQUENCY_KEY))
            clear_cooldown()
            self.scheduler.add_job(check_ontology_updates, 'date', run_date=datetime.utcnow())
            self.scheduler.reschedule_job(self.job_id, trigger='interval', minutes=interval, start_date=datetime.utcnow())

    def __new__(cls, *args, **kwargs):
        if not Scheduler.instance:
            Scheduler.instance = Scheduler.__Scheduler()
        return Scheduler.instance

    def __getattr__(self, item):
        return getattr(self.instance, item)

    def __setattr__(self, key, value):
        return setattr(self.instance, key, value)

    def update_interval(self):
        self.instance.update_interval()
