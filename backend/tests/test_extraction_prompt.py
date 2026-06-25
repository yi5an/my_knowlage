"""Regression tests for the entity extraction prompt.

Locks in the quality constraints (negative examples + canonical-key guidance)
so future prompt edits don't silently regress entity quality.
"""

from __future__ import annotations

from app.services.youtube.extraction_prompts import build_entity_extraction_prompt


def test_prompt_contains_negative_examples() -> None:
    prompt = build_entity_extraction_prompt("some text")

    # Perspective/role descriptions must be explicitly excluded.
    assert "视角" in prompt
    # Action/process descriptions must be excluded.
    assert "向量乘以一个数" in prompt
    # Fragment / single-char noise must be excluded.
    assert "pe" in prompt


def test_prompt_contains_canonical_key_guidance() -> None:
    prompt = build_entity_extraction_prompt("some text")

    # normalized_name must be shared across language/abbreviations.
    assert "normalized_name" in prompt
    assert "nvidia" in prompt.lower() or "英伟达" in prompt


def test_prompt_keeps_saliency_limit() -> None:
    prompt = build_entity_extraction_prompt("some text")
    assert "15" in prompt


def test_prompt_includes_known_types_hint() -> None:
    prompt = build_entity_extraction_prompt(
        "text", known_types=["person", "organization"]
    )
    assert "person" in prompt
    assert "organization" in prompt
