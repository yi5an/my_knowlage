from __future__ import annotations

import re
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import EntityType
from app.schemas.entities import EntityTypeSuggestionSchema
from app.services.structured_output import StructuredOutputClient


class EntityTypeDiscoveryService:
    def __init__(self, session: Session, llm_client: StructuredOutputClient | None = None) -> None:
        self.session = session
        self.llm_client = llm_client

    def discover(
        self,
        workspace_id: str,
        sample_text: str,
        limit: int,
    ) -> list[EntityTypeSuggestionSchema]:
        suggestions = self._rule_suggestions(sample_text)
        if self.llm_client is not None:
            prompt = f"Suggest entity types as JSON. Do not activate them.\n\n{sample_text}"
            suggestions.extend(
                self.llm_client.generate(prompt, EntityTypeSuggestionList).suggestions
            )
        unique = _dedupe_suggestions(suggestions)[:limit]
        for suggestion in unique:
            self._persist_suggestion(workspace_id, suggestion)
        self.session.commit()
        return unique

    def _rule_suggestions(self, sample_text: str) -> list[EntityTypeSuggestionSchema]:
        suggestions: list[EntityTypeSuggestionSchema] = []
        if re.search(r"NVDA|股票代码|交易所|NASDAQ|纳斯达克", sample_text, re.IGNORECASE):
            suggestions.append(
                EntityTypeSuggestionSchema(
                    name="stock",
                    domain="finance",
                    description="上市公司和股票证券实体",
                    examples=["英伟达", "NVDA"],
                    aliases=["股票", "上市公司"],
                    confidence=0.92,
                    evidence="文本包含股票代码、交易所或上市公司线索。",
                )
            )
        if "产业链" in sample_text or re.search(r"上游|中游|下游", sample_text):
            suggestions.append(
                EntityTypeSuggestionSchema(
                    name="industry_chain_node",
                    domain="industry",
                    description="产业链上下游节点",
                    examples=["上游材料", "中游制造", "下游应用"],
                    aliases=["产业链环节"],
                    confidence=0.9,
                    evidence="文本包含产业链阶段描述。",
                )
            )
        return suggestions

    def _persist_suggestion(
        self,
        workspace_id: str,
        suggestion: EntityTypeSuggestionSchema,
    ) -> None:
        statement = select(EntityType).where(
            EntityType.workspace_id == workspace_id,
            EntityType.name == suggestion.name,
        )
        if self.session.scalar(statement) is not None:
            return
        self.session.add(
            EntityType(
                id=f"etype_{uuid4().hex}",
                workspace_id=workspace_id,
                name=suggestion.name,
                domain=suggestion.domain,
                description=suggestion.description,
                examples=suggestion.examples,
                aliases=suggestion.aliases,
                source="discovery",
                status="suggested",
                confidence=suggestion.confidence,
            )
        )


class EntityTypeSuggestionList(BaseModel):
    suggestions: list[EntityTypeSuggestionSchema] = Field(default_factory=list)


def _dedupe_suggestions(
    suggestions: list[EntityTypeSuggestionSchema],
) -> list[EntityTypeSuggestionSchema]:
    deduped: dict[str, EntityTypeSuggestionSchema] = {}
    for suggestion in suggestions:
        current = deduped.get(suggestion.name)
        if current is None or suggestion.confidence > current.confidence:
            deduped[suggestion.name] = suggestion
    return list(deduped.values())
