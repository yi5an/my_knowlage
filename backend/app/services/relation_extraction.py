from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Entity, EntityRelation, RelationType
from app.schemas.entities import ExtractedRelationSchema, RelationExtractionSchema
from app.services.structured_output import StructuredOutputClient


class RelationExtractionService:
    def __init__(self, session: Session, llm_client: StructuredOutputClient | None = None) -> None:
        self.session = session
        self.llm_client = llm_client

    def extract(
        self,
        text: str,
        workspace_id: str,
        doc_id: str,
        chunk_id: str | None = None,
    ) -> RelationExtractionSchema:
        relations = self._extract_rule_relations(text, workspace_id, doc_id, chunk_id)
        if self.llm_client is not None:
            prompt = f"Extract relations as structured JSON with evidence.\n\n{text}"
            relations.extend(self.llm_client.generate(prompt, RelationExtractionSchema).relations)
        return RelationExtractionSchema(relations=relations)

    def extract_and_persist(
        self,
        text: str,
        workspace_id: str,
        doc_id: str,
        chunk_id: str | None = None,
    ) -> list[EntityRelation]:
        schema = self.extract(text, workspace_id, doc_id, chunk_id)
        persisted: list[EntityRelation] = []
        for item in schema.relations:
            relation_type = self._get_or_create_relation_type(workspace_id, item.relation_type)
            relation = EntityRelation(
                id=f"relation_{uuid4().hex}",
                workspace_id=workspace_id,
                source_entity_id=item.source_entity_id,
                target_entity_id=item.target_entity_id,
                relation_type_id=relation_type.id,
                evidence_doc_id=item.evidence_doc_id,
                evidence_chunk_id=item.evidence_chunk_id,
                evidence_text=item.evidence_text,
                confidence=item.confidence,
                verified=item.confidence >= 0.7,
                properties=item.properties,
            )
            self.session.add(relation)
            persisted.append(relation)
        self.session.commit()
        return persisted

    def _extract_rule_relations(
        self,
        text: str,
        workspace_id: str,
        doc_id: str,
        chunk_id: str | None,
    ) -> list[ExtractedRelationSchema]:
        relations: list[ExtractedRelationSchema] = []
        supply_pattern = r"([\w\u4e00-\u9fff]+)\s*(?:供应|供给|提供)\s*([\w\u4e00-\u9fff]+)"
        for source, target in re.findall(supply_pattern, text):
            source_entity = self._find_entity(workspace_id, source)
            target_entity = self._find_entity(workspace_id, target)
            if source_entity is None or target_entity is None:
                continue
            relations.append(
                ExtractedRelationSchema(
                    source_entity_id=source_entity.id,
                    target_entity_id=target_entity.id,
                    relation_type="supplies",
                    evidence_doc_id=doc_id,
                    evidence_chunk_id=chunk_id,
                    evidence_text=text,
                    confidence=0.72,
                    properties={"extractor": "regex"},
                )
            )
        return relations

    def _find_entity(self, workspace_id: str, text: str) -> Entity | None:
        normalized = text.lower()
        statement = select(Entity).where(
            Entity.workspace_id == workspace_id,
            Entity.normalized_name == normalized,
        )
        entity = self.session.scalar(statement)
        if entity is not None:
            return entity
        statement = select(Entity).where(
            Entity.workspace_id == workspace_id,
            Entity.name == text,
        )
        return self.session.scalar(statement)

    def _get_or_create_relation_type(self, workspace_id: str, name: str) -> RelationType:
        statement = select(RelationType).where(
            RelationType.workspace_id == workspace_id,
            RelationType.name == name,
        )
        relation_type = self.session.scalar(statement)
        if relation_type is not None:
            return relation_type
        relation_type = RelationType(
            id=f"rtype_{uuid4().hex}",
            workspace_id=workspace_id,
            name=name,
            description=f"Extracted relation type: {name}",
        )
        self.session.add(relation_type)
        self.session.flush()
        return relation_type
