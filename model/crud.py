from ckan.model import Session
import logging
from difflib import SequenceMatcher
from sqlalchemy import case, func, text
from sqlalchemy.exc import ProgrammingError
from ckanext.semantictags.model.vocabulary import Vocabulary, vocabulary_table
from ckanext.semantictags.model.tag import Tag, tag_table

log = logging.getLogger(__name__)


class VocabularyQuery:

    m = Vocabulary
    cols = [c.name for c in vocabulary_table.c]

    @classmethod
    def create(cls, name):
        '''
        Create a new record in the vocabulary table.

        :param name: the name of the vocabulary/ontology (e.g., 'oeo')
        :return: the newly created record object
        '''
        new_record = Vocabulary(name=name)
        Session.add(new_record)
        Session.commit()
        return new_record
    
    @classmethod
    def read(cls, identifier):
        '''
        Retrieve a vocabulary record by id.

        :param identifier: the vocabulary id (UUID)
        :return: the record object
        '''
        return Session.query(Vocabulary).get(identifier)
    
    @classmethod
    def read_name(cls, name):
        '''
        Retrieve a vocabulary record by name.

        :param name: the vocabulary name
        :return: the record object
        '''
        return Session.query(Vocabulary).filter(Vocabulary.name == name).first()
    
    @classmethod
    def read_or_create(cls, name):
        '''
        Retrieve a vocabulary by name, or create it if it doesn't exist.

        :param name: the vocabulary name
        :return: the record object
        '''
        record = cls.read_name(name)
        if record is None:
            record = cls.create(name)
        return record
    
    @classmethod
    def update(cls, identifier, **kwargs):
        '''
        Update fields of a vocabulary record.

        :param identifier: the vocabulary id
        :param kwargs: the values to be updated
        :return: the updated record object
        '''
        update_dict = {k: v for k, v in kwargs.items() if k in cls.cols}
        Session.query(Vocabulary).filter(Vocabulary.id == identifier).update(update_dict)
        Session.commit()
        return cls.read(identifier)
    
    @classmethod
    def delete(cls, identifier):
        '''
        Delete a vocabulary and all its associated tags.

        :param identifier: the vocabulary id
        :return: True if a record was deleted, False if not
        '''
        to_delete = cls.read(identifier)
        if to_delete is not None:
            # First delete all tags in this vocabulary
            TagQuery.delete_vocabulary(identifier)
            # Then delete the vocabulary
            Session.delete(to_delete)
            Session.commit()
            return True
        return False
    
    @classmethod
    def delete_name(cls, name):
        '''
        Delete a vocabulary by name.

        :param name: the vocabulary name
        :return: True if a record was deleted, False if not
        '''
        record = cls.read_name(name)
        if record is not None:
            return cls.delete(record.id)
        return False
    
    @classmethod
    def list(cls):
        '''
        List all vocabularies.

        :return: list of all vocabulary records
        '''
        return Session.query(Vocabulary).all()
    
class TagQuery:

    m = Tag
    cols = [c.name for c in tag_table.c]
    close_match_similarity = 0.3
    close_match_ratio = 0.6
    close_match_candidate_limit = 1000

    @classmethod
    def _pg_trgm_enabled(cls):
        try:
            res = Session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            )
            available = res.first() is not None
            log.debug("pg_trgm extension available: %s", available)
            return available
        except Exception:
            log.debug("pg_trgm extension check failed", exc_info=True)
            return False

    @classmethod
    def create(cls, name, vocabulary_id, iri=None, ontology=None):
        '''
        Create a new record in the tag table.

        :param name: the tag name/label
        :param vocabulary_id: the id of the vocabulary this tag belongs to
        :param iri: the IRI for this tag (optional)
        :return: the newly created record object
        '''
        # TODO: replace problematic characters
        
        new_record = Tag(name=name, vocabulary_id=vocabulary_id)
        Session.add(new_record)
        Session.flush() 

        update_fields = {}
        if iri:
            update_fields['iri'] = iri
        if ontology:
            update_fields['ontology'] = ontology
        if update_fields:
            set_clause = ", ".join([f"{k} = :{k}" for k in update_fields])
            update_fields['id'] = new_record.id
            Session.execute(
                f"UPDATE tag SET {set_clause} WHERE id = :id",
                update_fields
            )

        Session.commit()
        return new_record
    
    @classmethod
    def read(cls, identifier):
        '''
        Retrieve a tag record by id.

        :param identifier: the tag id (UUID)
        :return: the record object
        '''
        return Session.query(Tag).get(identifier)
    
    @classmethod
    def read_name(cls, name, vocabulary_id=None):
        '''
        Retrieve a tag record by name.

        :param name: the tag name
        :param vocabulary_id: optional vocabulary id to filter by
        :return: the record object
        '''
        query = Session.query(Tag).filter(Tag.name == name)
        if vocabulary_id is not None:
            query = query.filter(Tag.vocabulary_id == vocabulary_id)
        return query.first()
    
    @classmethod
    def read_iri(cls, iri):
        '''
        Retrieve a tag record by IRI.

        :param iri: the tag IRI
        :return: the record object
        '''
        return Session.query(Tag).filter(Tag.iri == iri).first()

    @classmethod
    def update(cls, identifier, **kwargs):
        '''
        Update fields of a tag record.

        :param identifier: the tag id
        :param kwargs: the values to be updated
        :return: the updated record object
        '''
        update_dict = {k: v for k, v in kwargs.items() if k in cls.cols}
        Session.query(Tag).filter(Tag.id == identifier).update(update_dict)
        Session.commit()
        return cls.read(identifier)

    @classmethod
    def delete(cls, identifier):
        '''
        Delete a tag by id.

        :param identifier: the tag id
        :return: True if a record was deleted, False if not
        '''
        to_delete = cls.read(identifier)
        if to_delete is not None:
            Session.delete(to_delete)
            Session.commit()
            return True
        return False
    
    @classmethod
    def delete_vocabulary(cls, vocabulary_id):
        '''
        Delete all tags belonging to a vocabulary.

        :param vocabulary_id: the vocabulary id
        :return: the number of records deleted
        '''
        count = Session.query(Tag).filter(Tag.vocabulary_id == vocabulary_id).delete()
        Session.commit()
        return count

    @classmethod
    def list_(cls, vocabulary_id):
        '''
        List all tags in a vocabulary.

        :param vocabulary_id: the vocabulary id
        :return: list of tag records
        '''
        return Session.query(Tag).filter(Tag.vocabulary_id == vocabulary_id).all()


    @classmethod
    def search(cls, query, vocabulary_id=None, limit=10):
        '''
        Search for tags by name (case-insensitive substring match)

        :param query: the search string
        :param vocabulary_id: optional vocabulary id to filter by
        :param limit: maximum number of results (default: 10)
        :return: list of matching tag records
        '''
        if not query:
            return []

        query = query.strip()
        if not query:
            return []

        base = Session.query(Tag)
        if vocabulary_id is not None:
            base = base.filter(Tag.vocabulary_id == vocabulary_id)
        else:
            # Only return tags that belong to a vocabulary
            base = base.filter(Tag.vocabulary_id.isnot(None))

        query_lower = query.lower()
        name_lower = func.lower(Tag.name)
        rank = case(
            [
                (name_lower == query_lower, 0),
                (name_lower.startswith(query_lower), 1),
            ],
            else_=2,
        )

        initial = (
            base.filter(name_lower.contains(query_lower))
            .order_by(rank, name_lower)
            .limit(limit)
            .all()
        )

        results = list(initial)
        if len(results) >= limit:
            return results

        seen_ids = {t.id for t in results}
        remaining = limit - len(results)

        # Use pg_trgm similarity (if available)
        if remaining > 0 and cls._pg_trgm_enabled():
            try:
                similarity = func.similarity(func.lower(Tag.name), query_lower)
                trigram_q = base.filter(similarity >= cls.close_match_similarity)

                if seen_ids:
                    trigram_q = trigram_q.filter(~Tag.id.in_(seen_ids))

                trigram = trigram_q.order_by(
                    similarity.desc(),
                    func.length(Tag.name),
                    func.lower(Tag.name),
                ).limit(remaining).all()

                results.extend(trigram)
                seen_ids.update(t.id for t in trigram)
                remaining = limit - len(results)

            except ProgrammingError:
                Session.rollback()

        # Fallback:  use difflib SequenceMatcher
        if remaining > 0:
            candidates = base.with_entities(Tag.id, Tag.name)

            if seen_ids:
                candidates = candidates.filter(~Tag.id.in_(seen_ids))
            candidates = candidates.limit(cls.close_match_candidate_limit).all()

            scored = []
            for tag_id, name in candidates:
                ratio = SequenceMatcher(None, query_lower, name.lower()).ratio()
                if ratio >= cls.close_match_ratio:
                    scored.append((ratio, tag_id))

            if scored:
                scored.sort(reverse=True)
                ids = [tag_id for _, tag_id in scored[:remaining]]

                if ids:
                    id_to_rank = {tag_id: idx for idx, tag_id in enumerate(ids)}
                    tags = base.filter(Tag.id.in_(ids)).all()
                    tags.sort(key=lambda t: id_to_rank.get(t.id, 0))
                    results.extend(tags)

        return results
    

class OntologyManager:

    @classmethod
    def add_ontology(cls, ontology_name, terms):
        '''
        Add or replace an ontology with its terms.

        :param ontology_name: name of the ontology (e.g., 'oeo')
        :param terms: list of dicts with 'label' and 'iri' keys
        :return: the vocabulary record
        '''
        # Get or create vocabulary
        vocab = VocabularyQuery.read_name(ontology_name)
        
        if vocab is not None:
            # Clear existing tags
            TagQuery.delete_vocabulary(vocab.id)
        else:
            # Create new vocabulary
            vocab = VocabularyQuery.create(ontology_name)
        
        # Add all terms as tags
        for term in terms:
            TagQuery.create(
                name=term['label'],
                vocabulary_id=vocab.id,
                iri=term.get('iri'),
                ontology=term.get('ontology') or ontology_name
            )
        
        return vocab
    
    @classmethod
    def delete_ontology(cls, ontology_name):
        '''
        Delete an ontology and all its terms.

        :param ontology_name: name of the ontology
        :return: True if deleted, False if not found
        '''
        return VocabularyQuery.delete_name(ontology_name)
    
    @classmethod
    def list_ontologies(cls):
        '''
        List all available ontologies.

        :return: list of dicts with 'id' and 'name' keys
        '''
        vocabs = VocabularyQuery.list()
        return [{'id': v.id, 'name': v.name} for v in vocabs]

    @classmethod
    def search_terms(cls, query, ontology_name=None, limit=10):
        '''
        Search for terms across ontologies.

        :param query: the search string
        :param ontology_name: optional ontology name to filter by
        :param limit: maximum number of results (default: 10)
        :return: list of dicts with term information
        '''
        vocabulary_id = None
        if ontology_name:
            vocab = VocabularyQuery.read_name(ontology_name)
            if vocab:
                vocabulary_id = vocab.id
        
        return TagQuery.search(query, vocabulary_id, limit)
