"""Prompt builder for batch investment-item translation (EN/other -> Chinese).

Used by :class:`InvestmentTranslationService` to translate the (often English)
title/summary of fetched investment items into Simplified Chinese so the
feed/calendar/digest read naturally for a Chinese user.
"""

from __future__ import annotations

from app.infrastructure.models import InvestmentItem


def build_investment_translation_prompt(items: list[InvestmentItem]) -> str:
    """Build the batch translation prompt for up to N items.

    Each item is sent with its id + title + summary. The LLM returns a
    ``InvestmentTranslationSchema`` with ``[{item_id, title_zh, summary_zh}]``.
    """
    if not items:
        return "没有需要翻译的内容。直接输出 translations 为空数组的 JSON。"
    lines: list[str] = []
    for i, item in enumerate(items, start=1):
        summary = (item.summary or "").strip()
        lines.append(f'[{i}] item_id="{item.id}"')
        lines.append(f'title="{item.title}"')
        lines.append(f'summary="{summary}"' if summary else 'summary=""')
    block = "\n".join(lines)
    return (
        "你是金融/宏观经济领域的专业翻译。把下面投资信息条目的标题与摘要"
        "翻译成**简体中文**。\n\n"
        f"条目清单:\n{block}\n\n"
        "翻译规则:\n"
        "1. 金融/宏观术语使用规范中文学术译名(如 FOMC statement → FOMC 声明, "
        "federal funds rate → 联邦基金利率, Treasury yield → 国债收益率, "
        "CPI → 消费者价格指数, minutes → 会议纪要)。\n"
        "2. 已是中文的内容原样返回。\n"
        "3. 专有机构缩写(FOMC/FED/SEC/BLS)可保留英文缩写,但首次出现时在括号"
        "内补中文释义,例如「FOMC(联邦公开市场委员会)声明」。\n"
        "4. 公司/股票名优先用业界通行中文译名(如 Apple → 苹果, "
        "NVIDIA → 英伟达),无可信译名时保留原文。\n"
        "5. 数字、日期、百分比、代码(如 CIK/序列号)保持原样。\n"
        "6. 摘要为空的, summary_zh 返回空字符串。\n"
        "7. 严格保留每个条目的 item_id, 不要遗漏或新增。\n\n"
        "输出 InvestmentTranslationSchema JSON: translations 数组, "
        "每个元素含 item_id / title_zh / summary_zh。"
    )
