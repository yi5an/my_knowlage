from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    Entity,
    EntityMention,
    EntityType,
    IndustryChain,
    IndustryChainNode,
    StockProfile,
)
from app.schemas.entities import EntityExtractionSchema, ExtractedEntitySchema
from app.services.entity_resolution import EntityResolutionService
from app.services.structured_output import StructuredOutputClient

DEFAULT_ENTITY_TYPES = {
    "stock": "上市公司和股票证券",
    "financial_metric": "财务指标和经营指标",
    "industry_chain": "产业链",
    "industry_chain_node": "产业链节点",
}


@dataclass(frozen=True)
class PersistedEntityExtraction:
    entity: Entity
    mention: EntityMention


class EntityExtractionService:
    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient | None = None,
        resolution_service: EntityResolutionService | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        # Resolution service handles entity normalization (alias matching +
        # optional LLM-assisted merge). Auto-build one from the LLM client when
        # not explicitly provided, so existing callers (worker, tests) get the
        # improved dedup without each wiring it themselves.
        resolution: EntityResolutionService | None
        if resolution_service is not None:
            resolution = resolution_service
        elif llm_client is not None:
            resolution = EntityResolutionService(
                session=session, llm_client=llm_client
            )
        else:
            resolution = None
        self.resolution_service = resolution

    def extract(
        self,
        text: str,
        workspace_id: str,
        doc_id: str,
        chunk_id: str | None = None,
    ) -> EntityExtractionSchema:
        extracted = [
            *self._extract_stocks(text),
            *self._extract_financial_metrics(text),
            *self._extract_industry_chain_nodes(text),
        ]
        extracted.extend(self._extract_with_llm(text).entities)
        return EntityExtractionSchema(entities=_dedupe_entities(extracted))

    def extract_and_persist(
        self,
        text: str,
        workspace_id: str,
        doc_id: str,
        chunk_id: str | None = None,
    ) -> list[PersistedEntityExtraction]:
        schema = self.extract(text, workspace_id, doc_id, chunk_id)
        persisted: list[PersistedEntityExtraction] = []
        for item in schema.entities:
            entity_type = self._get_or_create_entity_type(workspace_id, item.entity_type)
            entity = self._get_or_create_entity(workspace_id, entity_type.id, item)
            mention = EntityMention(
                id=f"mention_{uuid4().hex}",
                workspace_id=workspace_id,
                entity_id=entity.id,
                doc_id=doc_id,
                chunk_id=chunk_id,
                mention_text=item.evidence_text,
                start_offset=item.start_offset,
                end_offset=item.end_offset,
                confidence=item.confidence,
                extractor=item.extractor,
            )
            self.session.add(mention)
            self._persist_specialized_profile(workspace_id, entity, item)
            persisted.append(PersistedEntityExtraction(entity=entity, mention=mention))
        self.session.commit()
        return persisted

    def _extract_stocks(self, text: str) -> list[ExtractedEntitySchema]:
        results: list[ExtractedEntitySchema] = []
        patterns = [
            re.compile(r"(?P<company>英伟达|NVIDIA|Nvidia)\s*[（(]?(?P<ticker>NVDA)[）)]?"),
            re.compile(r"(?P<ticker>NVDA)\s*[（(]?(?P<company>英伟达|NVIDIA|Nvidia)?[）)]?"),
        ]
        for pattern in patterns:
            for match in pattern.finditer(text):
                ticker = match.group("ticker").upper()
                company = match.groupdict().get("company") or ticker
                results.append(
                    ExtractedEntitySchema(
                        name=company,
                        entity_type="stock",
                        normalized_name=ticker,
                        aliases=list({company, ticker, "NVIDIA"}),
                        properties={
                            "company_name": company,
                            "ticker": ticker,
                            "exchange": "NASDAQ",
                            "industry": "Semiconductors",
                            "sector": "AI chips",
                        },
                        evidence_text=match.group(0),
                        start_offset=match.start(),
                        end_offset=match.end(),
                        confidence=0.95,
                        extractor="regex",
                    )
                )
        return results

    def _extract_financial_metrics(self, text: str) -> list[ExtractedEntitySchema]:
        metric_pattern = re.compile(
            r"(?P<metric>营收|收入|净利润|毛利率|市盈率|PE|P/E|revenue|gross margin)",
            re.IGNORECASE,
        )
        results: list[ExtractedEntitySchema] = []
        for match in metric_pattern.finditer(text):
            metric = match.group("metric")
            start = max(match.start() - 12, 0)
            end = min(match.end() + 28, len(text))
            evidence = text[start:end]
            results.append(
                ExtractedEntitySchema(
                    name=metric,
                    entity_type="financial_metric",
                    normalized_name=metric.lower(),
                    properties={"metric_name": metric, "context": evidence},
                    evidence_text=evidence,
                    start_offset=match.start(),
                    end_offset=match.end(),
                    confidence=0.86,
                    extractor="regex",
                )
            )
        return results

    def _extract_industry_chain_nodes(self, text: str) -> list[ExtractedEntitySchema]:
        stage_patterns = {
            "upstream": r"上游(?:包括|为|是)?(?P<value>[^。.;；\n]+)",
            "midstream": r"中游(?:包括|为|是)?(?P<value>[^。.;；\n]+)",
            "downstream": r"下游(?:包括|为|是)?(?P<value>[^。.;；\n]+)",
        }
        results: list[ExtractedEntitySchema] = []
        chain_match = re.search(r"(?P<name>[\w\u4e00-\u9fff]+产业链)", text)
        if chain_match:
            results.append(
                ExtractedEntitySchema(
                    name=chain_match.group("name"),
                    entity_type="industry_chain",
                    normalized_name=chain_match.group("name").lower(),
                    properties={"chain_name": chain_match.group("name")},
                    evidence_text=chain_match.group(0),
                    start_offset=chain_match.start(),
                    end_offset=chain_match.end(),
                    confidence=0.9,
                    extractor="dictionary",
                )
            )
        for stage, pattern in stage_patterns.items():
            for match in re.finditer(pattern, text):
                for name in _split_names(match.group("value")):
                    results.append(
                        ExtractedEntitySchema(
                            name=name,
                            entity_type="industry_chain_node",
                            normalized_name=name.lower(),
                            properties={"stage": stage, "node_type": "industry_chain_segment"},
                            evidence_text=match.group(0),
                            start_offset=match.start(),
                            end_offset=match.end(),
                            confidence=0.88,
                            extractor="dictionary",
                        )
                    )
        return results

    def _extract_with_llm(self, text: str) -> EntityExtractionSchema:
        if self.llm_client is None:
            return EntityExtractionSchema(entities=[])
        from app.services.youtube.extraction_prompts import build_entity_extraction_prompt

        prompt = build_entity_extraction_prompt(text)
        return self.llm_client.generate(prompt, EntityExtractionSchema)

    def _get_or_create_entity_type(self, workspace_id: str, name: str) -> EntityType:
        statement = select(EntityType).where(
            EntityType.workspace_id == workspace_id,
            EntityType.name == name,
        )
        entity_type = self.session.scalar(statement)
        if entity_type is not None:
            return entity_type
        entity_type = EntityType(
            id=f"etype_{uuid4().hex}",
            workspace_id=workspace_id,
            name=name,
            description=DEFAULT_ENTITY_TYPES.get(name),
            source="system",
            status="active",
            confidence=1.0,
        )
        self.session.add(entity_type)
        self.session.flush()
        return entity_type

    def _get_or_create_entity(
        self,
        workspace_id: str,
        entity_type_id: str,
        item: ExtractedEntitySchema,
    ) -> Entity:
        # Prefer the resolution service (alias + LLM matching) when injected.
        if self.resolution_service is not None:
            entity, _created = self.resolution_service.resolve(
                workspace_id, entity_type_id, item
            )
            return entity
        # Legacy fallback: exact normalized_name match only.
        statement = select(Entity).where(
            Entity.workspace_id == workspace_id,
            Entity.normalized_name == item.normalized_name,
        )
        existing = self.session.scalar(statement)
        if existing is not None:
            existing.confidence = max(existing.confidence, item.confidence)
            existing.properties = {**(existing.properties or {}), **item.properties}
            return existing
        entity = Entity(
            id=f"entity_{uuid4().hex}",
            workspace_id=workspace_id,
            entity_type_id=entity_type_id,
            name=item.name,
            normalized_name=item.normalized_name,
            aliases=item.aliases,
            properties=item.properties,
            confidence=item.confidence,
            verified=False,
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    def _persist_specialized_profile(
        self,
        workspace_id: str,
        entity: Entity,
        item: ExtractedEntitySchema,
    ) -> None:
        if item.entity_type == "stock" and self.session.get(StockProfile, entity.id) is None:
            self.session.add(
                StockProfile(
                    entity_id=entity.id,
                    ticker=str(item.properties.get("ticker", "")),
                    exchange=_optional_str(item.properties.get("exchange")),
                    company_name=_optional_str(item.properties.get("company_name")),
                    industry=_optional_str(item.properties.get("industry")),
                    sector=_optional_str(item.properties.get("sector")),
                    metadata_={"aliases": item.aliases},
                )
            )
        if item.entity_type == "industry_chain":
            new_chain = IndustryChain(
                id=f"chain_{uuid4().hex}",
                workspace_id=workspace_id,
                name=item.name,
                metadata_={"entity_id": entity.id},
            )
            self.session.add(new_chain)
        if item.entity_type == "industry_chain_node":
            existing_chain = self.session.scalar(
                select(IndustryChain).where(IndustryChain.workspace_id == workspace_id)
            )
            if existing_chain is not None:
                self.session.add(
                    IndustryChainNode(
                        id=f"chain_node_{uuid4().hex}",
                        chain_id=existing_chain.id,
                        entity_id=entity.id,
                        name=item.name,
                        stage=str(item.properties.get("stage", "unknown")),
                        node_type=_optional_str(item.properties.get("node_type")),
                    )
                )


def _dedupe_entities(items: list[ExtractedEntitySchema]) -> list[ExtractedEntitySchema]:
    deduped: dict[tuple[str, str], ExtractedEntitySchema] = {}
    for item in items:
        key = (item.entity_type, item.normalized_name)
        current = deduped.get(key)
        if current is None or item.confidence > current.confidence:
            deduped[key] = item
    return list(deduped.values())


def _split_names(value: str) -> list[str]:
    names = re.split(r"[、,，/和及]", value)
    return [name.strip() for name in names if name.strip()]


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
