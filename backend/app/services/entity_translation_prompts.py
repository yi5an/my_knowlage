"""Prompt builder for batch entity-name translation (EN/other -> Chinese).

Used by :class:`EntityTranslationService` to give each entity a Chinese name
(``properties.zh_name``) so the graph can display bilingual labels. Entities
are sent in a single batch to keep LLM cost down.
"""

from __future__ import annotations

from app.infrastructure.models import Entity


def build_entity_translation_prompt(entities: list[Entity]) -> str:
    if not entities:
        return "没有需要翻译的实体。直接输出空的 EntityTranslationResult JSON。"
    lines = []
    for i, entity in enumerate(entities, start=1):
        lines.append(f'[{i}] id={entity.id} name="{entity.name}"')
    block = "\n".join(lines)
    return (
        "你是专业术语翻译。把下面实体名称翻译成**简体中文规范译名**。\n\n"
        f"实体清单:\n{block}\n\n"
        "翻译规则:\n"
        "1. 公司/产品/技术名优先使用业界通行中文译名(如 NVIDIA→英伟达, "
        "Micron→美光, OpenAI→开放人工智能)。\n"
        "2. 已是中文的名称,原样返回(如「英伟达」→「英伟达」)。\n"
        "3. 没有公认中文译名的专有名词(人名/品牌),保留原文。\n"
        "4. 概念/术语用规范中文学术译名(如 semiconductor memory→半导体存储, "
        "Artificial intelligence→人工智能)。\n\n"
        "为每个实体输出 entity_id 和 zh_name(中文译名)。\n"
        "输出 EntityTranslationResult JSON。"
    )
