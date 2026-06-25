"""Prompt builders for LLM-based entity and relation extraction.

These produce domain-agnostic prompts so any video transcript (AI,
finance, science, ...) yields usable entities and relations for the
knowledge graph. The prompts are kept here rather than inline so the
quality can be tuned without touching service code.
"""

from __future__ import annotations


def build_entity_extraction_prompt(
    text: str, *, known_types: list[str] | None = None
) -> str:
    types_hint = ""
    if known_types:
        types_hint = (
            "Known entity types in this workspace: "
            + ", ".join(known_types)
            + ". Reuse these when applicable, but you may also propose new "
            "types if none fit.\n\n"
        )
    return (
        "Extract the most important named entities from the text below. "
        "Focus on entities that would help build a knowledge graph: people, "
        "organizations, products, technologies, concepts, places, and events. "
        "Skip generic words.\n\n"
        f"{types_hint}"
        "判定标准 —— 只有满足以下条件之一的才抽取为实体:\n"
        "1. 命名实体:具体的人名、公司/机构名、产品名、技术/标准名、地名、事件名。\n"
        "2. 重要概念:有独立知识图谱价值、可被多个来源引用的专业术语或概念"
        "(如「线性代数」「HBM」「向量」「标量」「Transformer」)。\n\n"
        "严禁抽取以下内容(它们不是实体):\n"
        "- 视角/角色/身份描述:如「数学家的视角」「物理学学生」「数据分析师」"
        "「计算机图形程序员」—— 这些是说话人的修辞,不是实体。\n"
        "- 操作/动作/过程描述:如「向量乘以一个数」「首尾相接法」「与数字的乘法」"
        "「张成空间」—— 这些是动作或过程,不是实体。\n"
        "- 句子片段/修饰语:如「有序的数字列表」「物理学家的视角」。\n"
        "- 单字或无意义碎片:如「pe」「x轴」(应归入规范的「坐标轴」)。\n"
        "- 同一概念的细碎变体:同一概念只抽取一次规范名(中英文择一),"
        "其余作为 aliases。\n\n"
        "For each entity provide:\n"
        "- name: the canonical name as it appears\n"
        "- entity_type: a short lowercase type like person, organization, "
        "product, technology, concept, place, event\n"
        "- normalized_name: lowercase canonical key for deduplication. "
        "Same entity in different languages/abbreviations must share one "
        "normalized_name (e.g. 英伟达/NVIDIA/NVDA -> \"nvidia\").\n"
        "- aliases: other names/short forms used in the text\n"
        "- evidence_text: a short verbatim snippet from the text\n"
        "- confidence: 0..1\n"
        "- extractor: \"llm\"\n\n"
        "Do NOT invent entities not supported by the text. Limit to the 15 "
        "most salient entities.\n\n"
        f"Text:\n{text}"
    )


def build_relation_extraction_prompt(
    text: str, *, known_entity_names: list[str] | None = None
) -> str:
    names_hint = ""
    if known_entity_names:
        names_hint = (
            "Entities already known in this text: "
            + ", ".join(known_entity_names[:40])
            + ". Prefer relations among these.\n\n"
        )
    return (
        "抽取文本中实体之间最重要的关系。使用实体在文本中出现的准确名称"
        "(source_entity_id 与 target_entity_id 是实体名称字符串)。\n\n"
        f"{names_hint}"
        "关系类型(relation_type)请优先使用以下标准化类型之一,用中文表示:\n"
        "- 竞争:两者是竞争对手关系\n"
        "- 合作:两者有合作/伙伴关系\n"
        "- 供应:前者向后者供应产品/服务(上游→下游)\n"
        "- 上游:前者是后者的上游供应商\n"
        "- 下游:前者是后者的下游客户\n"
        "- 投资:前者投资后者\n"
        "- 收购:前者收购后者\n"
        "- 依赖:前者依赖后者的产品/技术\n"
        "- 隶属:前者隶属于后者(part_of)\n"
        "- 驱动:前者驱动/带动后者的需求或增长\n"
        "- 研发:前者研发/开发后者\n"
        "- 使用:前者使用后者的产品/技术\n"
        "仅当上述类型都不合适时,才用一个简短中文动词短语描述\n"
        "(如「变革」「领先于」)。\n\n"
        "For each relation provide:\n"
        "- source_entity_id: 实体名称(string)\n"
        "- target_entity_id: 实体名称(string)\n"
        "- relation_type: 上述标准化中文类型之一\n"
        "- evidence_text: 支撑该关系的原文片段\n"
        "- confidence: 0..1\n\n"
        "只抽取文本明确支持的关系,不要编造。最多抽取 10 条最重要的关系。\n\n"
        f"Text:\n{text}"
    )
