from ckan.model.vocabulary import Vocabulary, vocabulary_table


def init_table():
    """
    Using CKAN's existing vocabulary table.
    """
    pass


__all__ = ['Vocabulary', 'vocabulary_table', 'init_table']
