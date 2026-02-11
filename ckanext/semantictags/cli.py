import logging

import ckan.model as model
import ckan.plugins.toolkit as toolkit
import click
from ckan.types import Context
from ckanext.semantictags.helpers import get_terms_by_ontology, FREE_TAGS_KEY, FORCE_RELOAD_KEY, generate_tag_vocabulary
from ckanext.semantictags.model import tag as tag_model
from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery

log = logging.getLogger(__name__)


def _ensure_default(key, default_value):
    context: Context = {
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


def get_commands():
    return [semantictags]


@click.group('semantictags')
def semantictags():
    pass


@semantictags.command('init')
def init():
    """
    Initialize SemanticTags runtime data:

    - ensure default config options exist in DB
    - optionally init DB tables
    - generate tag vocabulary (protected by PG advisory lock)
    """
    tag_model.init_table()
    click.echo("Database initialized.")

    allow_free_tags = _ensure_default(FREE_TAGS_KEY, 'false')
    force_reload = _ensure_default(FORCE_RELOAD_KEY, 'false')

    click.echo(f"{FREE_TAGS_KEY}={allow_free_tags}")
    click.echo(f"{FORCE_RELOAD_KEY}={force_reload}")

    if toolkit.asbool(force_reload):
        generate_tag_vocabulary()
        click.echo("Vocabulary generated.")
    else:
        click.echo("force_reload is false; skipping vocabulary generation.")


@semantictags.command()
@click.argument('ontology_name')
def load_ontology(ontology_name):
    """Load an ontology"""
    click.echo(f"Loading ontology: {ontology_name}")

    try:
        terms = get_terms_by_ontology(ontology_name)
        OntologyManager.add_ontology(ontology_name, terms)
        click.echo(f"Successfully loaded {len(terms)} terms for {ontology_name}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@semantictags.command()
@click.argument('ontology_name')
def delete_ontology(ontology_name):
    """Delete an ontology and all its terms"""
    if OntologyManager.delete_ontology(ontology_name):
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
@click.option('--ontology', '-o', default=None, help='Filter by ontology')
@click.option('--limit', '-l', default=10, help='Max results')
def search(query, ontology, limit):
    """Search for terms."""
    results = OntologyManager.search_terms(query, ontology, limit)
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
