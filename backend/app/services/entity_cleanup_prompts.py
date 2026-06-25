"""Prompt builder for LLM-assisted entity-quality review.

Used by :class:`EntityCleanupService` to decide whether each *existing* entity
in a workspace is a genuine, graph-worthy entity or noise (a perspective
description, an action, a sentence fragment, ...). Returns a valid/invalid
verdict per entity so low-quality ones can be removed.
"""

from __future__ import annotations

from app.infrastructure.models import Entity


def build_entity_cleanup_prompt(entities: list[Entity]) -> str:
    if not entities:
        return (
            "没有需要审查的实体。直接输出空的 EntityCleanupDecision JSON"
            "(reviews 为空数组)。"
        )
    lines = []
    for i, entity in enumerate(entities, start=1):
        lines.append(f'[{i}] id={entity.id} 名称="{entity.name}"')
    block = "\n".join(lines)
    return (
        "你是实体质量审查专家。下面是一个知识库中已存在的实体清单。"
        "请判断每个实体是否是一个**真正的、有知识图谱价值的实体**。\n\n"
        f"实体清单:\n{block}\n\n"
        "判定标准(满足任一即为 is_valid=true):\n"
        "1. 命名实体:具体的人名、公司/机构名、产品名、技术/标准名、地名、事件名。\n"
        "2. 重要概念:有独立知识图谱价值、可被多个来源引用的专业术语或概念"
        "(如「线性代数」「HBM」「向量」「Transformer」「英伟达」)。\n\n"
        "以下情况判 is_valid=false(它们不是实体,是噪声):\n"
        "- 视角/角色/身份描述:如「数学家的视角」「物理学学生」「数据分析师」。\n"
        "- 操作/动作/过程:如「向量乘以一个数」「首尾相接法」。\n"
        "- 句子片段/修饰语:如「有序的数字列表」「物理学家的视角」。\n"
        "- 单字或无意义碎片:如「pe」。\n"
        "- 过度细碎、与另一实体实质重复的变体。\n\n"
        "为每个实体输出 entity_id、is_valid、reason(一句话)。\n"
        "输出 EntityCleanupDecision JSON。"
    )
