import click
from ckanext.semantictags.model.crud import OntologyManager, TagQuery, VocabularyQuery
from ckanext.semantictags.model import tag as tag_model
from ckanext.semantictags.plugin import get_terms_by_ontology

import logging
log = logging.getLogger(__name__)


@click.group()
def semantictags():
    pass


@semantictags.command()
def initdb():
    """Initialize"""
    tag_model.init_table()
    click.echo("Database initialized.")


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
