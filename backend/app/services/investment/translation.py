"""Batch-translate investment items' title/summary to Simplified Chinese.

Fetched items (Fed RSS / SEC / BLS / FRED) are usually in English. This
service translates a batch of untranslated items (``title_zh IS NULL``) in a
single LLM call and writes back ``title_zh`` / ``summary_zh``.

By default this degrades gracefully: if the LLM client is missing/mock or the
call fails, items keep their original-language title/summary and nothing is
raised. User-triggered retries and background translation jobs can opt into
``raise_on_failure`` so real LLM/auth failures are visible instead of looking
like a successful no-op. Already-Chinese items are detected and skipped (their
``title_zh`` is set to the original so they're not re-processed).
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentItem
from app.schemas.investment import InvestmentTranslationSchema
from app.services.investment.translation_prompts import build_investment_translation_prompt
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)

# A CJK Unified Ideograph — enough to tell "this text is already Chinese".
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _looks_chinese(text: str | None) -> bool:
    """True if ``text`` contains at least one CJK ideograph."""
    return bool(text and _CJK_RE.search(text))


class InvestmentTranslationService:
    """Batch-translate untranslated investment items to Simplified Chinese."""

    def __init__(self, session: Session, llm_client: StructuredOutputClient | None) -> None:
        self.session = session
        self.llm_client = llm_client

    def translate_untranslated(
        self,
        workspace_id: str = "ws_default",
        limit: int = 20,
        *,
        raise_on_failure: bool = False,
    ) -> dict[str, int]:
        """Translate up to ``limit`` items lacking Chinese title or summary.

        Returns ``{"translated": N, "skipped": M}``. By default logs LLM
        failures and returns what got through; with ``raise_on_failure=True``,
        raises a RuntimeError so callers can surface the failure.
        """
        items = list(
            self.session.scalars(
                select(InvestmentItem)
                .where(
                    InvestmentItem.workspace_id == workspace_id,
                    (InvestmentItem.title_zh.is_(None))
                    | (
                        InvestmentItem.summary.is_not(None)
                        & InvestmentItem.summary_zh.is_(None)
                    ),
                )
                .order_by(InvestmentItem.created_at)
                .limit(limit)
            )
        )
        if not items:
            return {"translated": 0, "skipped": 0}

        # Already-Chinese fields are copied directly so they're not re-queried,
        # while mixed-language rows still go through the LLM for missing fields.
        to_translate: list[InvestmentItem] = []
        skipped = 0
        for item in items:
            needs_title = item.title_zh is None
            needs_summary = bool(item.summary and item.summary_zh is None)
            if needs_title and _looks_chinese(item.title):
                item.title_zh = item.title
                needs_title = False
            if needs_summary and _looks_chinese(item.summary):
                item.summary_zh = item.summary
                needs_summary = False
            if needs_title or needs_summary:
                to_translate.append(item)
            else:
                skipped += 1
        if skipped:
            self.session.commit()

        if not to_translate:
            return {"translated": 0, "skipped": skipped}

        if self.llm_client is None:
            logger.info("investment translation skipped: no LLM client configured")
            if raise_on_failure:
                raise RuntimeError("investment translation failed: no LLM client configured")
            return {"translated": 0, "skipped": skipped}

        try:
            result = self.llm_client.generate(
                build_investment_translation_prompt(to_translate),
                InvestmentTranslationSchema,
            )
        except Exception as exc:  # noqa: BLE001 — default mode must not block fetching
            logger.exception("investment translation LLM call failed; items keep original text")
            if raise_on_failure:
                raise RuntimeError(f"investment translation failed: {exc}") from exc
            return {"translated": 0, "skipped": skipped}

        id_to_translation = {t.item_id: t for t in result.translations}
        translated = 0
        for item in to_translate:
            t = id_to_translation.get(item.id)
            if t is None or not t.title_zh:
                continue
            changed = False
            if item.title_zh is None:
                item.title_zh = t.title_zh
                changed = True
            if item.summary and item.summary_zh is None:
                item.summary_zh = t.summary_zh if t.summary_zh else item.summary
                changed = True
            if changed:
                translated += 1
        if translated:
            self.session.commit()
        logger.info(
            "investment translation: %d translated, %d skipped (of %d pending)",
            translated,
            skipped,
            len(items),
        )
        return {"translated": translated, "skipped": skipped}
