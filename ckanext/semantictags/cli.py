import logging

import ckan.model as model
import ckan.plugins.toolkit as toolkit
import click

from ckanext.semantictags.helpers import get_terms_by_ontology, FREE_TAGS_KEY, FORCE_RELOAD_KEY, generate_tag_vocabulary, LDM_tags_util
from ckanext.semantictags.model import tag as tag_model
from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery

log = logging.getLogger(__name__)


def _ensure_default(key, default_value):
    context = {
        'ignore_auth': True,
        'model': model,
        'session': model.Session
    }

    show = toolkit.get_action('config_option_show')
    update = toolkit.get_action('config_option_update')

    try:
        value = show(context, {'key': key})
    except toolkit.ObjectNotFound:
        value = None

    if value is None or value == '':
        update(context, {key: default_value})
        value = default_value

    return value


def _get_vocab():
    tags_util = LDM_tags_util()
    return VocabularyQuery.read_or_create(tags_util.vocabulary_name_default)


def get_commands():
    return [semantictags]


@click.group('semantictags')
def semantictags():
    pass


@semantictags.command('init')
@click.option('--free-tags/--no-free-tags', default=False, help='Allow free tags by default')
@click.option('--force-reload/--no-force-reload', default=False, help='Force reload of vocabularies by default')
def init(free_tags, force_reload):
    """
    Initialize ckanext-semantictags runtime data:

    - initializes the database table
    - ensures default config options are set
    - generates tag vocabulary

    The default values for free tags and force reloading are only considered if no value was
    previously set in the CKAN configuration. CKAN configuration values have precedence.
    """
    tag_model.init_table()
    click.echo("Database initialized.")

    _ensure_default(FREE_TAGS_KEY, free_tags)
    _ensure_default(FORCE_RELOAD_KEY, force_reload)

    generate_tag_vocabulary()


@semantictags.command()
@click.argument('ontology_name')
def load_ontology(ontology_name):
    """Load an ontology"""
    click.echo(f"Loading ontology: {ontology_name}")

    try:
        terms = get_terms_by_ontology(ontology_name)
        vocab = _get_vocab()
        OntologyManager.add_ontology(vocab.id, ontology_name, terms)
        click.echo(f"Successfully loaded {len(terms)} terms for {ontology_name}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@semantictags.command()
@click.argument('ontology_name')
def delete_ontology(ontology_name):
    """Delete an ontology and all its terms"""
    vocab = _get_vocab()
    if OntologyManager.delete_ontology(vocab.id, ontology_name):
        click.echo(f"Deleted ontology: {ontology_name}")
    else:
        click.echo(f"Ontology not found: {ontology_name}", err=True)


@semantictags.command()
def list_ontologies():
    """List all available ontologies"""
    ontologies = OntologyManager.list_ontologies()
    if ontologies:
        for ont in ontologies:
            click.echo(f"- {ont['name']} (id: {ont['id']})")
    else:
        click.echo("No ontologies found.")


@semantictags.command()
@click.argument('query')
@click.option('--limit', '-l', default=10, help='Max results')
def search(query, limit):
    """Search for terms."""
    results = OntologyManager.search_terms(query, limit)
    if results:
        for term in results:
            click.echo(f"- {term.name} | {getattr(term, 'iri', None)} | {getattr(term, 'ontology', None)}")
    else:
        click.echo("No results found.")


@semantictags.command()
@click.argument('name')
@click.argument('ontology')
@click.option('--iri', default=None, help='IRI for the tag')
@click.option('--vocabulary', '-v', default=None, help='Vocabulary name (defaults to ontology)')
def add_tag(name, ontology, iri, vocabulary):
    """Add a single tag with ontology metadata."""
    name = name.replace(',', '_').replace('/', '_')
    vocab_name = vocabulary or ontology
    vocab = VocabularyQuery.read_or_create(vocab_name)
    TagQuery.create(name=name, vocabulary_id=vocab.id, iri=iri, ontology=ontology)
    click.echo(f"Added tag '{name}' to vocab '{vocab_name}' with ontology '{ontology}'.")
