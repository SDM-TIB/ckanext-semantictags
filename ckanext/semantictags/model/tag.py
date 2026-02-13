from ckan.model import Session
from ckan.model.tag import Tag, tag_table 


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
        return True
    return False


def init_table():
    """
    Initialize the tag table extension.
    """
    add_iri_column()
    add_ontology_column()

__all__ = ['Tag', 'tag_table', 'add_iri_column', 'add_ontology_column', 'init_table']
