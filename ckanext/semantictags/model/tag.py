import logging

from ckan.model import Session
from ckan.model.tag import Tag, tag_table
from sqlalchemy import Column, UnicodeText
from sqlalchemy.orm import configure_mappers

log = logging.getLogger(__name__)


def add_iri_column():
    """
    Add iri column to CKAN's existing tag table
    """
    result = Session.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'tag' AND column_name = 'iri'
    """)

    if result.fetchone() is None:
        Session.execute('ALTER TABLE tag ADD COLUMN iri TEXT')
        Session.commit()
        log.info('Added iri column to tag table')
        return True
    return False


def add_ontology_column():
    """
    Add ontology column to CKAN's existing tag table
    """
    result = Session.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'tag' AND column_name = 'ontology'
    """)

    if result.fetchone() is None:
        Session.execute('ALTER TABLE tag ADD COLUMN ontology TEXT')
        Session.commit()
        log.info('Added ontology column to tag table')
        return True
    return False


def add_label_column():
    """
    Add label column to CKAN's existing tag table
    """
    result = Session.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'tag' AND column_name = 'label'
    """)

    if result.fetchone() is None:
        Session.execute('ALTER TABLE tag ADD COLUMN label TEXT')
        Session.commit()
        log.info('Added label column to tag table')
        return True
    return False


def extend_tag_model():
    """
    Extend CKAN's Tag model to include the new columns.
    This makes SQLAlchemy aware of the columns so they can be properly accessed.
    """
    # Add columns to CKAN's existing tag_table definition
    if not hasattr(tag_table.c, 'iri'):
        iri_col = Column('iri', UnicodeText)
        iri_col._creation_order = 9999
        tag_table.append_column(iri_col)
        log.debug('Added iri column to tag_table definition')

    if not hasattr(tag_table.c, 'ontology'):
        ontology_col = Column('ontology', UnicodeText)
        ontology_col._creation_order = 9999
        tag_table.append_column(ontology_col)
        log.debug('Added ontology column to tag_table definition')

    if not hasattr(tag_table.c, 'label'):
        label_col = Column('label', UnicodeText)
        label_col._creation_order = 9999
        tag_table.append_column(label_col)
        log.debug('Added label column to tag_table definition')

    # Set default values on the Tag class so existing tags don't throw AttributeError
    if not hasattr(Tag, 'iri'):
        Tag.iri = None
    if not hasattr(Tag, 'ontology'):
        Tag.ontology = None
    if not hasattr(Tag, 'label'):
        Tag.label = None

    # Reconfigure mappers to recognize the new columns
    try:
        configure_mappers()
        log.info('Tag model extended with iri, ontology, and label')
    except Exception as e:
        log.debug(f'Mapper reconfiguration info: {e}')


def init_table():
    """
    Initialize the tag table extension.
    """
    # First add columns to the database
    add_iri_column()
    add_ontology_column()
    add_label_column()

    # Then extend the SQLAlchemy model
    extend_tag_model()


__all__ = ['Tag', 'tag_table', 'add_iri_column', 'add_ontology_column', 'add_label_column', 'init_table']
