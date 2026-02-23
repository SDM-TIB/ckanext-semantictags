from ckan.model import Session
import logging
from collections import Counter
from sqlalchemy import case, func, text
from sqlalchemy.exc import ProgrammingError
from ckanext.semantictags.model.vocabulary import Vocabulary, vocabulary_table
from ckanext.semantictags.model.tag import Tag, tag_table
from ckan.lib.munge import munge_tag

log = logging.getLogger(__name__)


class VocabularyQuery:

    m = Vocabulary
    cols = [c.name for c in vocabulary_table.c]

    @classmethod
    def create(cls, name):
        """
        Create a new record in the vocabulary table.

        :param name: the name of the vocabulary/ontology (e.g., 'oeo')
        :return: the newly created record object
        """
        new_record = Vocabulary(name=name)
        Session.add(new_record)
        Session.commit()
        return new_record
    
    @classmethod
    def read(cls, identifier):
        """
        Retrieve a vocabulary record by id.

        :param identifier: the vocabulary id (UUID)
        :return: the record object
        """
        return Session.query(Vocabulary).get(identifier)
    
    @classmethod
    def read_name(cls, name):
        """
        Retrieve a vocabulary record by name.

        :param name: the vocabulary name
        :return: the record object
        """
        return Session.query(Vocabulary).filter(Vocabulary.name == name).first()
    
    @classmethod
    def read_or_create(cls, name):
        """
        Retrieve a vocabulary by name, or create it if it doesn't exist.

        :param name: the vocabulary name
        :return: the record object
        """
        record = cls.read_name(name)
        if record is None:
            record = cls.create(name)
        return record
    
    @classmethod
    def update(cls, identifier, **kwargs):
        """
        Update fields of a vocabulary record.

        :param identifier: the vocabulary id
        :param kwargs: the values to be updated
        :return: the updated record object
        """
        update_dict = {k: v for k, v in kwargs.items() if k in cls.cols}
        Session.query(Vocabulary).filter(Vocabulary.id == identifier).update(update_dict)
        Session.commit()
        return cls.read(identifier)
    
    @classmethod
    def delete(cls, identifier):
        """
        Delete a vocabulary and all its associated tags.

        :param identifier: the vocabulary id
        :return: True if a record was deleted, False if not
        """
        to_delete = cls.read(identifier)
        if to_delete is not None:
            # First delete all tags in this vocabulary
            TagQuery.delete_by_vocabulary(identifier)
            # Then delete the vocabulary
            Session.delete(to_delete)
            Session.commit()
            return True
        return False
    
    @classmethod
    def list(cls):
        """
        List all vocabularies.

        :return: list of all vocabulary records
        """
        return Session.query(Vocabulary).all()


class TagQuery:

    m = Tag
    cols = [c.name for c in tag_table.c]
    close_match_similarity = 0.3
    close_match_candidate_limit = 1000
    _row_columns = (
        Tag.id,
        Tag.name,
        Tag.vocabulary_id,
        tag_table.c.iri,
        tag_table.c.ontology,
        tag_table.c.label,
    )

    @classmethod
    def _row_to_tag(cls, row):
        if row is None:
            return None
        tag = Tag(name=row.name, vocabulary_id=row.vocabulary_id)
        tag.id = row.id
        tag.iri = row.iri
        tag.ontology = row.ontology
        tag.label = row.label
        return tag

    @staticmethod
    def _trigrams(text):
        if text is None:
            return []
        padded = f"  {text}  "
        return [padded[i:i + 3] for i in range(len(padded) - 2)]

    @classmethod
    def _trigram_similarity(cls, left, right):
        left_tris = cls._trigrams(left)
        right_tris = cls._trigrams(right)
        if not left_tris or not right_tris:
            return 0.0
        left_counts = Counter(left_tris)
        right_counts = Counter(right_tris)
        shared = sum((left_counts & right_counts).values())
        return (2.0 * shared) / (len(left_tris) + len(right_tris))

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
    def create(cls, name, vocabulary_id, iri=None, ontology=None, label=None):
        """
        Create a new record in the tag table.

        :param name: the tag name/label (munged)
        :param vocabulary_id: the id of the vocabulary this tag belongs to
        :param iri: the IRI for this tag (optional)
        :param ontology: the ontology this tag belongs to (optional)
        :param label: the original display label (optional)
        :return: the newly created record object
        """
        
        new_record = Tag(name=name, vocabulary_id=vocabulary_id)
        Session.add(new_record)
        Session.flush()

        if iri or ontology or label:
            update_values = {}
            if iri:
                update_values['iri'] = iri
            if ontology:
                update_values['ontology'] = ontology
            if label:
                update_values['label'] = label

            Session.execute(
                tag_table.update().where(tag_table.c.id == new_record.id).values(**update_values)
            )

        Session.commit()
        return cls.read(new_record.id)
    
    @classmethod
    def read(cls, identifier):
        """
        Retrieve a tag record by id.

        :param identifier: the tag id (UUID)
        :return: the record object
        """
        row = Session.query(*cls._row_columns).filter(Tag.id == identifier).first()
        return cls._row_to_tag(row)
    
    @classmethod
    def read_name(cls, name, vocabulary_id=None):
        """
        Retrieve a tag record by name.

        :param name: the tag name
        :param vocabulary_id: optional vocabulary id to filter by
        :return: the record object
        """
        query = Session.query(Tag).filter(Tag.name == name)
        if vocabulary_id is not None:
            query = query.filter(Tag.vocabulary_id == vocabulary_id)
        return query.first()
    
    @classmethod
    def read_iri(cls, iri):
        """
        Retrieve a tag record by IRI.

        :param iri: the tag IRI
        :return: the record object
        """
        return Session.query(Tag).filter(Tag.iri == iri).first()

    @classmethod
    def update(cls, identifier, **kwargs):
        """
        Update fields of a tag record.

        :param identifier: the tag id
        :param kwargs: the values to be updated
        :return: the updated record object
        """
        update_dict = {k: v for k, v in kwargs.items() if k in cls.cols}
        Session.query(Tag).filter(Tag.id == identifier).update(update_dict)
        Session.commit()
        return cls.read(identifier)

    @classmethod
    def delete(cls, identifier):
        """
        Delete a tag by id.

        :param identifier: the tag id
        :return: True if a record was deleted, False if not
        """
        to_delete = cls.read(identifier)
        if to_delete is not None:
            Session.delete(to_delete)
            Session.commit()
            return True
        return False
    
    @classmethod
    def delete_by_vocabulary(cls, vocabulary_id):
        """
        Delete all tags belonging to a vocabulary.

        :param vocabulary_id: the vocabulary id
        :return: the number of records deleted
        """
        count = Session.query(Tag).filter(Tag.vocabulary_id == vocabulary_id).delete()
        Session.commit()
        return count

    @classmethod
    def list_(cls, vocabulary_id):
        """
        List all tags in a vocabulary.

        :param vocabulary_id: the vocabulary id
        :return: list of tag records
        """
        return Session.query(Tag).filter(Tag.vocabulary_id == vocabulary_id).all()

    @classmethod
    def search(cls, query, vocabulary_id=None, limit=10):
        """
        Search for tags by name (case-insensitive substring match)

        :param query: the search string
        :param vocabulary_id: optional vocabulary id to filter by
        :param limit: maximum number of results (default: 10)
        :return: list of matching tag records
        """
        if not query:
            return []

        query = query.strip()
        if not query:
            return []

        base = Session.query(*cls._row_columns)
    
        if vocabulary_id is not None:
            base = base.filter(Tag.vocabulary_id == vocabulary_id)
        else:
            base = base.filter(Tag.vocabulary_id.isnot(None))

        query_lower = query.lower()
        name_lower = func.lower(Tag.name)
        label_lower = func.lower(func.coalesce(tag_table.c.label, Tag.name))

        rank = case(
            [
                (name_lower == query_lower, 0),
                (label_lower == query_lower, 0),
                (name_lower.startswith(query_lower), 1),
                (label_lower.startswith(query_lower), 1),
            ],
            else_=2,
        )

        initial = (
            base.filter(
                (name_lower.contains(query_lower)) |
                (label_lower.contains(query_lower))
            )
            .order_by(rank, label_lower)
            .limit(limit)
            .all()
        )

        results = [cls._row_to_tag(row) for row in initial]
        if len(results) >= limit:
            return results

        seen_ids = {t.id for t in results}
        remaining = limit - len(results)

        # Use pg_trgm similarity (if available)
        if remaining > 0 and cls._pg_trgm_enabled():
            try:
                label_or_name = func.coalesce(tag_table.c.label, Tag.name)
                similarity = func.similarity(func.lower(label_or_name), query_lower)

                trigram_base = Session.query(*cls._row_columns)

                if vocabulary_id is not None:
                    trigram_base = trigram_base.filter(Tag.vocabulary_id == vocabulary_id)
                else:
                    trigram_base = trigram_base.filter(Tag.vocabulary_id.isnot(None))

                trigram_q = trigram_base.filter(similarity >= cls.close_match_similarity)

                if seen_ids:
                    trigram_q = trigram_q.filter(~Tag.id.in_(seen_ids))

                trigram_rows = trigram_q.order_by(
                    similarity.desc(),
                    func.length(label_or_name),
                    func.lower(label_or_name),
                ).limit(remaining).all()

                for row in trigram_rows:
                    tag = cls._row_to_tag(row)
                    results.append(tag)
                    seen_ids.add(tag.id)

                remaining = limit - len(results)

            except ProgrammingError:
                Session.rollback()

        # Fallback: approximate pg_trgm similarity in Python
        if remaining > 0:
            candidates_base = Session.query(*cls._row_columns)

            if vocabulary_id is not None:
                candidates_base = candidates_base.filter(Tag.vocabulary_id == vocabulary_id)
            else:
                candidates_base = candidates_base.filter(Tag.vocabulary_id.isnot(None))

            if seen_ids:
                candidates_base = candidates_base.filter(~Tag.id.in_(seen_ids))

            candidate_rows = candidates_base.limit(cls.close_match_candidate_limit).all()

            scored = []
            for row in candidate_rows:
                tag_id, name, vocab_id, iri, ont, label = row
                # Use label for matching, fall back to name if label is None
                search_text = (label or name or "").lower()
                if not search_text:
                    continue
                similarity = cls._trigram_similarity(query_lower, search_text)
                if similarity >= cls.close_match_similarity:
                    scored.append((similarity, len(search_text), search_text, row))

            if scored:
                scored.sort(reverse=True)
                top_rows = [row for _, _, _, row in scored[:remaining]]

                for row in top_rows:
                    results.append(cls._row_to_tag(row))

        return results
        

class OntologyManager:

    @classmethod
    def get_loaded_ontologies(cls, vocabulary_id):
        """Get list of ontologies already loaded in a vocabulary."""
        result = Session.execute(
            text("""
                SELECT DISTINCT ontology 
                FROM tag 
                WHERE vocabulary_id = :vocab_id 
                AND ontology IS NOT NULL
            """),
            {'vocab_id': vocabulary_id}
        )
        return set(row[0] for row in result.fetchall())

    @classmethod
    def is_ontology_loaded(cls, vocabulary_id, ontology_name):
        """Check if an ontology is already loaded."""
        result = Session.execute(
            text("""
                SELECT COUNT(*) 
                FROM tag 
                WHERE vocabulary_id = :vocab_id 
                AND ontology = :ontology
            """),
            {'vocab_id': vocabulary_id, 'ontology': ontology_name}
        )
        return result.fetchone()[0] > 0
    
    @classmethod
    def add_ontology(cls, vocabulary_id, ontology_name, terms, refresh_existing=False):
        """
        Add or replace an ontology with its terms.

        :param ontology_name: name of the ontology (e.g., 'oeo')
        :param terms: list of dicts with 'label' and 'iri' keys
        :param refresh_existing: whether to update existing tags for the ontology
        :return: the vocabulary record
        """

        # Reattach existing tags from ontology to vocabulary 
        Session.execute(
            text("""
                UPDATE tag
                SET vocabulary_id = :vocab_id
                WHERE ontology = :ontology
                AND vocabulary_id IS NULL
            """),
            {'vocab_id': vocabulary_id, 'ontology': ontology_name}
        )
        Session.commit()
        seen = set()
        count = 0
        for term in terms:
            label = term.get('label')
            if not label:
                continue
            name = munge_tag(label)
            key = term.get('iri') or name
            if not key or key in seen:
                continue
            seen.add(key)
            ontology_value = term.get('ontology') or ontology_name
            existing = Session.query(Tag.id, Tag.vocabulary_id).filter(
                Tag.name == name,
                tag_table.c.ontology == ontology_value
            ).first()
            if existing:
                update_values = {}
                if existing.vocabulary_id != vocabulary_id:
                    update_values['vocabulary_id'] = vocabulary_id
                iri = term.get('iri')
                if iri is not None:
                    update_values['iri'] = iri
                if refresh_existing:
                    update_values['ontology'] = ontology_value
                    update_values['label'] = label
                if update_values:
                    Session.execute(
                        tag_table.update().where(tag_table.c.id == existing.id).values(**update_values)
                    )
                    Session.commit()
                continue
            try:
                TagQuery.create(
                    name=name,
                    vocabulary_id=vocabulary_id,
                    iri=term.get('iri'),
                    ontology=ontology_value,
                    label=label
                )
                count += 1
            except Exception as e:
                log.debug(f"Tag '{name}' already exists, skipping")
                Session.rollback()
                continue
        log.debug(f"Added {count} terms for ontology: {ontology_name}")
        return count
    
    @classmethod
    def delete_ontology(cls, vocabulary_id, ontology_name):
        """
        Delete all tags for a specific ontology.

        :param vocabulary_id: the vocabulary id
        :param ontology_name: name of the ontology
        :return: number of tags deleted
        """
        detached = Session.execute(
            text("""
                UPDATE tag
                SET vocabulary_id = NULL
                WHERE vocabulary_id = :vocab_id
                AND ontology = :ontology
                AND id IN (SELECT tag_id FROM package_tag)
            """),
            {'vocab_id': vocabulary_id, 'ontology': ontology_name}
        )

        deleted = Session.execute(
            text("""
                DELETE FROM tag
                WHERE vocabulary_id = :vocab_id
                AND ontology = :ontology
                AND id NOT IN (SELECT tag_id FROM package_tag)
            """),
            {'vocab_id': vocabulary_id, 'ontology': ontology_name}
        )
        Session.commit()
        count = detached.rowcount + deleted.rowcount
        log.debug(f"Detached {detached.rowcount} tags and deleted {deleted.rowcount} tags from ontology: {ontology_name}")
        return count
    
    @classmethod
    def list_ontologies(cls):
        """
        List all available ontologies.

        :return: list of dicts with 'id' and 'name' keys
        """
        vocabs = VocabularyQuery.list()
        return [{'id': v.id, 'name': v.name} for v in vocabs]
    
    @classmethod
    def search_terms(cls, query, limit=10, vocabulary_id=None):
        """
        Search for terms across ontologies.

        :param query: the search string
        :param limit: maximum number of results (default: 10)
        :return: list of matching tag records
        """
        return TagQuery.search(query, vocabulary_id=vocabulary_id, limit=limit)
