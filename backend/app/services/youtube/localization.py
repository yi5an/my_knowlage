"""Helpers for identifying YouTube summaries that still need Chinese output."""

from __future__ import annotations

import re

from app.schemas.youtube import SummaryResult

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]{2,}\b")


def _summary_text(summary: SummaryResult) -> str:
    parts = [summary.tldr]
    parts.extend(point.point for point in summary.key_points)
    parts.extend(quote.text for quote in summary.quotes)
    parts.extend(chapter.title for chapter in summary.chapters)
    return "\n".join(part for part in parts if part)


def needs_chinese_localization(summary: SummaryResult) -> bool:
    """Return True when a completed summary appears to be mostly non-Chinese."""
    text = _summary_text(summary)
    if not text.strip():
        return False

    cjk_count = len(_CJK_RE.findall(text))
    latin_words = _LATIN_WORD_RE.findall(text)

    if cjk_count >= 4:
        return False
    return len(latin_words) >= 6
