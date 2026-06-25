"""Prompt builders for the deep-research workflow nodes.

Each builder turns the node's runtime state (the question, gathered sources,
draft claims) into a self-contained user prompt for the
``StructuredOutputClient``. Prompts are kept here, separate from the service,
so the workflow code reads as orchestration rather than string assembly.

Mirrors the layout of ``services/youtube/extraction_prompts.py``.
"""

from __future__ import annotations

from app.schemas.research import ResearchClaim, ResearchSourceItem


def build_plan_prompt(question: str) -> str:
    """PlanResearchNode: decompose a research question into retrieval queries."""
    return (
        "你是一个研究规划专家。给定一个研究问题,请把它拆解成 2-4 个用于检索的子查询,"
        "覆盖问题的不同侧面(例如:定义、现状、对比、趋势、风险)。\n\n"
        f"研究问题: {question}\n\n"
        "要求:\n"
        "1. 子查询用与问题相同的语言。\n"
        "2. 每条子查询应是一条可直接用于知识库检索或网络搜索的短语。\n"
        "3. rationale 用一句话说明拆解思路。\n\n"
        "输出 ResearchPlan JSON。"
    )


def _render_sources(sources: list[ResearchSourceItem]) -> str:
    if not sources:
        return "(暂无来源)"
    lines = []
    for i, src in enumerate(sources, start=1):
        origin = src.url or src.doc_id or src.source_type
        lines.append(
            f"[来源 {i}] 标题: {src.title}\n"
            f"  类型: {src.source_type} | 链接/文档: {origin}\n"
            f"  片段: {src.snippet}"
        )
    return "\n\n".join(lines)


def build_extract_claims_prompt(
    question: str, sources: list[ResearchSourceItem]
) -> str:
    """ExtractClaimsNode: extract factual claims with evidence + confidence."""
    sources_block = _render_sources(sources)
    return (
        "你是一个严谨的研究分析员。下面是围绕研究问题收集到的若干来源片段。\n"
        "请从这些片段中抽取与问题相关的**事实性主张(claims)**。\n\n"
        f"研究问题: {question}\n\n"
        f"来源片段:\n{sources_block}\n\n"
        "要求:\n"
        "1. 每个 claim 的 text 是一句完整、可独立成立的事实陈述。\n"
        "2. evidence 列出支撑该主张的来源标题(可多条)。\n"
        "3. confidence ∈ [0,1]:来源越权威、表述越确定,分数越高;推断或孤证给较低分。\n"
        "4. 只抽取来源**明确支持**的主张,不要编造来源中没有的信息。\n"
        "5. 使用与来源一致的语言。\n\n"
        "输出 ExtractedClaims JSON。"
    )


def build_cross_check_prompt(
    question: str, claims: list[ResearchClaim]
) -> str:
    """CrossCheckNode: cross-validate claims, adjust confidence, flag conflict."""
    if not claims:
        return (
            f"研究问题: {question}\n\n"
            "当前没有任何主张需要交叉验证。直接输出空的 CrossCheckedClaims JSON。"
        )
    lines = []
    for i, claim in enumerate(claims, start=1):
        evidence = "; ".join(claim.evidence) if claim.evidence else "(无)"
        lines.append(
            f"[主张 {i}] (conf={claim.confidence:.2f}) {claim.text}\n  证据: {evidence}"
        )
    claims_block = "\n\n".join(lines)
    return (
        "你是一个交叉验证专家。下面是从多个来源抽取的主张。请对它们进行交叉验证:\n\n"
        f"研究问题: {question}\n\n"
        f"待验证主张:\n{claims_block}\n\n"
        "要求:\n"
        "1. 合并重复或近义的主张(保留信息最完整的一条)。\n"
        "2. 若多个独立来源支持同一主张,confidence 应上调;孤证或相互矛盾的主张下调。\n"
        "3. 直接删除与问题无关、或与其它来源明显冲突且无法调和的主张。\n"
        "4. confidence 最终值必须落在 [0,1]。\n"
        "5. evidence 保留原始来源标题即可,不要新增。\n\n"
        "输出 CrossCheckedClaims JSON。"
    )


def build_report_prompt(
    question: str,
    title: str,
    sources: list[ResearchSourceItem],
    claims: list[ResearchClaim],
) -> str:
    """GenerateReportNode: synthesize the final structured report."""
    sources_block = _render_sources(sources)
    if claims:
        claims_block = "\n".join(
            f"- (conf={c.confidence:.2f}) {c.text}" for c in claims
        )
    else:
        claims_block = "(暂无主张)"
    return (
        "你是一个研究报告撰写专家。基于以下来源与已验证的主张,撰写一份结构化研究报告。\n\n"
        f"研究主题: {title}\n"
        f"研究问题: {question}\n\n"
        f"来源:\n{sources_block}\n\n"
        f"已验证主张:\n{claims_block}\n\n"
        "报告必须包含以下全部字段,且为结构化 JSON:\n"
        "- summary: 一段话概括研究结论(围绕问题作答)。\n"
        "- background: 研究背景与问题缘起。\n"
        "- key_findings: 3-6 条关键发现(来自已验证主张)。\n"
        "- evidence: 支撑结论的证据来源标题列表。\n"
        "- comparison_table: 来源对比表,每行含 source(标题)、type(类型)、"
        "credibility(可信度字符串)。\n"
        "- risks_and_uncertainties: 数据缺口、来源局限、未决问题。\n"
        "- next_steps: 2-4 条后续可深入的方向。\n\n"
        "要求:\n"
        "1. 所有文字使用与研究问题一致的语言。\n"
        "2. 不要编造来源或主张中没有的事实。\n"
        "3. credibility 写成 0-1 之间的数字字符串,如 \"0.85\"。\n\n"
        "输出 ResearchReport JSON。"
    )
