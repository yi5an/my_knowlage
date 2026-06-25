"""Prompt builder for LLM-assisted entity-merge decisions.

Used by :class:`EntityResolutionService` and :class:`EntityMergeService` when
alias matching is inconclusive but names show token overlap. The model gets a
batch of candidate pairs and returns a same/different verdict per pair.

Conservative by design: the prompt tells the model to answer ``is_same=false``
unless it is confident the two entities refer to the same real-world thing.
"""

from __future__ import annotations

from app.schemas.entities import EntityMergePair


def build_entity_merge_prompt(pairs: list[EntityMergePair]) -> str:
    if not pairs:
        return (
            "没有需要判定的实体对。直接输出空的 EntityMergeDecision JSON"
            "(decisions 为空数组)。"
        )
    lines = []
    for i, pair in enumerate(pairs, start=1):
        a_aliases = "、".join(pair.entity_a_aliases) if pair.entity_a_aliases else "无"
        b_aliases = "、".join(pair.entity_b_aliases) if pair.entity_b_aliases else "无"
        lines.append(
            f"[{i}] a_id={pair.entity_a_id} 名称=\"{pair.entity_a_name}\" 别名={a_aliases}\n"
            f"    b_id={pair.entity_b_id} 名称=\"{pair.entity_b_name}\" 别名={b_aliases}"
        )
    pairs_block = "\n".join(lines)
    return (
        "你是实体消歧专家。下面是若干**疑似重复**的实体对(它们来自同一个知识库,"
        "且名称存在一定重叠)。请判断每一对中的两个实体是否指向**现实中的同一个事物**"
        "(例如同一个公司、同一个产品、同一个概念)。\n\n"
        f"候选实体对:\n{pairs_block}\n\n"
        "判定规则:\n"
        "1. 只有两者的名称、别名足以确认指向同一对象时,才判 is_same=true。\n"
        "   例如「英伟达」与「NVIDIA」(别名互相覆盖) → true;\n"
        "   「英伟达」与「英特尔」 → false。\n"
        "2. 只要存在合理疑虑(它们可能是不同的公司/产品/概念),就判 is_same=false"
        "(宁可保留重复也不要错误合并)。\n"
        "3. 缩写与全称、中英文互译、简称与全称 → 视为同一对象(true)。\n"
        "4. 仅名称字面相似但语义不同的(如「AI芯片」与「芯片」) → false。\n\n"
        "为每一对输出 entity_a_id、entity_b_id、is_same、reason(一句话理由)。\n\n"
        "输出 EntityMergeDecision JSON。"
    )
