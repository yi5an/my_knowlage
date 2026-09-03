"""Prompts for structured provenance event extraction."""

from __future__ import annotations

from app.infrastructure.models import EvidenceAnchor


def build_event_extraction_prompt(anchors: list[EvidenceAnchor]) -> str:
    lines = [
        "你是事件抽取助手。只能使用下方已持久化的证据锚点，不得补充外部知识。",
        "每个事件必须引用一个或多个下方 evidence_anchor_id。",
        "只返回来源中明确表达的事件，不要把相似度当作因果关系。",
    ]
    for anchor in anchors:
        lines.append(f"[{anchor.id}] ({anchor.anchor_type}) {anchor.quote}")
    return "\n\n".join(lines)
