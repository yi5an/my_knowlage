from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.provenance import (
    ConclusionLinkOutput,
    EvidenceLocator,
    ImageRegionLocator,
    MediaSegmentLocator,
    PdfRegionLocator,
    ProvenanceGraphResponse,
    TextSpanLocator,
    WebFragmentLocator,
)


def test_text_span_rejects_reversed_offsets() -> None:
    with pytest.raises(ValidationError):
        TextSpanLocator(chunk_id="chunk-1", start_offset=8, end_offset=4)


def test_pdf_region_rejects_bbox_outside_normalized_space() -> None:
    with pytest.raises(ValidationError):
        PdfRegionLocator(page_no=1, bbox=(0.1, 0.2, 1.2, 0.8))


def test_media_segment_requires_increasing_time() -> None:
    with pytest.raises(ValidationError):
        MediaSegmentLocator(start_ms=9_000, end_ms=2_000)


def test_image_region_accepts_ocr_blocks() -> None:
    locator = ImageRegionLocator(
        frame_id="frame-1",
        bbox=(0.1, 0.2, 0.8, 0.9),
        ocr_block_ids=["ocr-1"],
    )
    assert locator.type == "image_region"


def test_web_fragment_requires_capture_time() -> None:
    locator = WebFragmentLocator(
        fragment_id="fragment-1",
        selector="article p:nth-child(2)",
        captured_at="2026-09-03T08:00:00Z",
    )
    assert locator.captured_at.tzinfo is not None


def test_locator_union_is_discriminated() -> None:
    locator = TypeAdapter(EvidenceLocator).validate_python(
        {
            "type": "text_span",
            "chunk_id": "chunk-1",
            "start_offset": 0,
            "end_offset": 7,
        }
    )
    assert isinstance(locator, TextSpanLocator)


def test_ai_link_requires_evidence_anchor_ids() -> None:
    with pytest.raises(ValidationError):
        ConclusionLinkOutput(
            source_backing_type="knowledge_event",
            source_backing_id="event-1",
            target_conclusion_id="conclusion-1",
            relation_type="supports",
            rationale="The event supports the conclusion.",
            confidence=0.8,
            evidence_anchor_ids=[],
        )


def test_graph_response_exposes_degradation_and_counts() -> None:
    response = ProvenanceGraphResponse(
        nodes=[],
        edges=[],
        clusters=[],
        graph_version="v1",
        degraded=True,
        degraded_reason="graph_store_unavailable",
        total_nodes=7,
        returned_nodes=0,
        has_more=True,
        next_cursor="cursor-1",
    )
    assert response.degraded is True
    assert response.total_nodes == 7
    assert response.next_cursor == "cursor-1"
