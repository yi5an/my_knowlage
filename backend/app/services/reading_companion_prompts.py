from __future__ import annotations

from app.schemas.reading_companion import (
    CorroborationVerdictSchema,
    ReadingInsightExtractionSchema,
)
from app.services.reading_evidence import ReadingEvidenceCandidate

PROMPT_VERSION = "reading-companion-v1"


def build_insight_prompt(*, title: str, chunk_id: str, content: str) -> str:
    return f"""你是本地知识库的陪读助手。只分析给出的正文，不得补充外部事实，不得给出交易建议。
为最多 3 个高价值片段输出 JSON。每个片段必须包含原文中的 evidence_text、
对应 chunk_id、字符范围、解释、重要性和置信度。
文档标题: {title}
chunk_id: {chunk_id}
正文:\n{content}\n
输出必须符合 {ReadingInsightExtractionSchema.__name__}。"""


def build_corroboration_prompt(
    *,
    headline: str,
    explanation: str,
    candidates: list[ReadingEvidenceCandidate],
) -> str:
    source_lines = "\n".join(
        f"[{candidate.source_id}] {candidate.title}: {candidate.excerpt}"
        for candidate in candidates
    )
    return f"""你是证据核验助手。只可依据给定候选资料判断，不得补充外部事实或交易建议。
待核验阅读结论：{headline}\n{explanation}
候选资料：\n{source_lines}
只输出有直接证据的 supports、contradicts 或 contextualizes；没有直接证据时返回空列表。
输出必须符合 {CorroborationVerdictSchema.__name__}。"""
