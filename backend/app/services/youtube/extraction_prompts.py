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
        "For each entity provide:\n"
        "- name: the canonical name as it appears\n"
        "- entity_type: a short lowercase type like person, organization, "
        "product, technology, concept, place, event\n"
        "- normalized_name: lowercase canonical key for deduplication\n"
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
        "Extract the most important relationships between entities mentioned "
        "in the text. Use entity names exactly as they appear (source_entity_id "
        "and target_entity_id should be the entity name strings).\n\n"
        f"{names_hint}"
        "For each relation provide:\n"
        "- source_entity_id: entity name (string)\n"
        "- target_entity_id: entity name (string)\n"
        "- relation_type: a short lowercase verb phrase like develops, "
        "competes_with, founded, acquired, part_of, uses, mentions\n"
        "- evidence_text: a short verbatim snippet supporting the relation\n"
        "- confidence: 0..1\n\n"
        "Only extract relations directly supported by the text. Limit to the "
        "10 most salient relations.\n\n"
        f"Text:\n{text}"
    )
