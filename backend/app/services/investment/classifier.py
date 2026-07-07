"""GLM-5.2 classifier for investment items.

Classifies an item's text into suggested impact fields using the shared
:class:`StructuredOutputClient`. The LLM only ever writes ``suggested_*`` shadow
fields plus ``classification_reason``; the user-confirmed fields
(``importance`` / ``impact_direction`` / ``impact_horizon`` / ``thesis_impact``)
are NEVER overwritten here (doc 04 §6, §17.3). The item stays
``action_status='pending_review'`` until the user confirms.

System rules (doc 04 §15): judge only from input text; opinion-layer content
must not be treated as established fact; no buy/sell/hold advice.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentItem
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)


class InvestmentClassificationSchema(BaseModel):
    """Structured-output contract for the classifier (doc 04 §15)."""

    importance: str = Field(description="low | medium | high")
    impact_direction: str = Field(description="positive | negative | neutral | uncertain")
    impact_horizon: str = Field(description="short | mid | long | unknown")
    thesis_impact: str = Field(description="supports | weakens | contradicts | unrelated | unknown")
    reason: str = Field(description="简短中文理由")
    claims: list[dict[str, object]] = Field(
        default_factory=list,
        description="可选：从文本中抽取的待验证观点列表",
    )


SYSTEM_RULES = """你是投资研究信息分层助手。规则：
1. 只能基于输入文本判断，不得补充未出现的事实。
2. 观点层(opinion)内容默认不能当作事实结论，可信度必须较低。
3. 如果来源是一手公告或宏观官方数据，可信度可高；个人观点必须低。
4. 不要给出买入、卖出、持有建议，只判断信息影响。
5. 严格输出给定 JSON schema。"""


def _build_prompt(item: InvestmentItem) -> str:
    text_parts = [item.title]
    if item.summary:
        text_parts.append(item.summary)
    text = "\n".join(text_parts)
    return (
        f"{SYSTEM_RULES}\n\n"
        f"信息层级: {item.info_layer}\n"
        f"来源可信度: {item.source_credibility}\n"
        f"来源: {item.source_name or '未知'}\n\n"
        f"文本:\n{text}\n\n"
        f"请输出 JSON 分类结果。"
    )


_VALID = {
    "importance": {"low", "medium", "high"},
    "impact_direction": {"positive", "negative", "neutral", "uncertain"},
    "impact_horizon": {"short", "mid", "long", "unknown"},
    "thesis_impact": {"supports", "weakens", "contradicts", "unrelated", "unknown"},
}


def _coerce(value: str, valid: set[str], default: str) -> str:
    return value if value in valid else default


class InvestmentClassifier:
    """Classify items via the structured-output LLM client."""

    def __init__(self, session: Session, llm_client: StructuredOutputClient) -> None:
        self.session = session
        self.llm_client = llm_client

    def classify_item(self, item_id: str) -> InvestmentClassificationSchema:
        """Run the classifier on one item and persist suggested_* fields.

        Raises if the item is missing. Network/LLM failures propagate as
        ``StructuredOutputError`` (the client retries internally).
        """
        item = self.session.get(InvestmentItem, item_id)
        if item is None:
            raise ValueError(f"investment item {item_id!r} not found")

        prompt = _build_prompt(item)
        result = self.llm_client.generate(prompt, InvestmentClassificationSchema)

        # Persist ONLY the suggested shadow fields; confirmed fields untouched.
        item.suggested_importance = _coerce(result.importance, _VALID["importance"], "medium")
        item.suggested_impact_direction = _coerce(
            result.impact_direction, _VALID["impact_direction"], "uncertain"
        )
        item.suggested_impact_horizon = _coerce(
            result.impact_horizon, _VALID["impact_horizon"], "unknown"
        )
        item.suggested_thesis_impact = _coerce(
            result.thesis_impact, _VALID["thesis_impact"], "unknown"
        )
        item.classification_reason = result.reason
        # IMPORTANT: do not set action_status away from pending_review, and do
        # not touch the confirmed importance/direction/horizon/thesis_impact.
        self.session.commit()
        logger.info("classified investment item %s: %s", item_id, result.importance)
        return result
