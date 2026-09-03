import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../services/client";
import type { TraceEdgeDetail } from "../../types/provenance";
import { EvidenceAuditDrawer } from "./EvidenceAuditDrawer";

const edge: TraceEdgeDetail = {
  id: "edge-1",
  source_id: "evidence-1",
  target_id: "event-1",
  relation_type: "supports",
  rationale: "原始证据支持该事件判断",
  confidence: 0.84,
  review_status: "pending_review",
  validation_status: "supported",
  origin_type: "ai",
  evidence_anchor_ids: ["anchor-1", "anchor-2", "anchor-3", "anchor-4"],
  version_no: 3,
  model_metadata: { model: "reasoner-v2", prompt_version: "trace-4" },
  review_history: [{ action: "reset_pending", reviewer_id: "analyst" }],
  evidence: [
    {
      id: "anchor-1",
      workspace_id: "ws",
      document_id: "doc-1",
      version_id: "ver-1",
      chunk_id: "chunk-1",
      source_item_id: null,
      anchor_type: "text_span",
      locator: { type: "text_span", chunk_id: "chunk-1", start_offset: 4, end_offset: 22 },
      quote: "精确文本证据",
      content_hash: "hash",
      source_uri_snapshot: null,
      source_quality: 0.9,
      validation_state: "valid",
      created_by_type: "ai",
      created_by_id: null,
      supersedes_anchor_id: null,
      created_at: "2026-09-03T00:00:00Z",
    },
    {
      id: "anchor-2",
      workspace_id: "ws",
      document_id: "pdf-doc",
      version_id: "ver-2",
      chunk_id: null,
      source_item_id: null,
      anchor_type: "pdf_region",
      locator: { type: "pdf_region", page_no: 7, bbox: [0.1, 0.2, 0.7, 0.8] },
      quote: "PDF 区域",
      content_hash: "hash",
      source_uri_snapshot: null,
      source_quality: 0.8,
      validation_state: "stale",
      created_by_type: "ai",
      created_by_id: null,
      supersedes_anchor_id: null,
      created_at: "2026-09-03T00:00:00Z",
    },
    {
      id: "anchor-3",
      workspace_id: "ws",
      document_id: "video-doc",
      version_id: "ver-3",
      chunk_id: null,
      source_item_id: null,
      anchor_type: "media_segment",
      locator: { type: "media_segment", start_ms: 1200, end_ms: 6400 },
      quote: "视频片段",
      content_hash: "hash",
      source_uri_snapshot: null,
      source_quality: 0.7,
      validation_state: "valid",
      created_by_type: "ai",
      created_by_id: null,
      supersedes_anchor_id: null,
      created_at: "2026-09-03T00:00:00Z",
    },
    {
      id: "anchor-4",
      workspace_id: "ws",
      document_id: "image-doc",
      version_id: "ver-4",
      chunk_id: null,
      source_item_id: null,
      anchor_type: "image_region",
      locator: { type: "image_region", frame_id: "frame-8", bbox: [0, 0.1, 0.5, 0.6], ocr_block_ids: [] },
      quote: "图像区域",
      content_hash: "hash",
      source_uri_snapshot: null,
      source_quality: 0.7,
      validation_state: "valid",
      created_by_type: "ai",
      created_by_id: null,
      supersedes_anchor_id: null,
      created_at: "2026-09-03T00:00:00Z",
    },
  ],
};

describe("EvidenceAuditDrawer", () => {
  it("shows edge audit metadata, evidence freshness, and precise locator links", () => {
    render(
      <MemoryRouter>
        <EvidenceAuditDrawer open edge={edge} onClose={vi.fn()} onReview={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByText("原始证据支持该事件判断")).toBeInTheDocument();
    expect(screen.getByText(/reasoner-v2/)).toBeInTheDocument();
    expect(screen.getByText("证据已过期")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "定位原文：精确文本证据" })).toHaveAttribute(
      "href",
      "/reader/doc-1?chunk=chunk-1&start=4&end=22",
    );
    expect(screen.getByRole("link", { name: "定位原文：PDF 区域" }).getAttribute("href")).toContain(
      "/reader/pdf-doc?page=7&bbox=0.1%2C0.2%2C0.7%2C0.8",
    );
    expect(screen.getByRole("link", { name: "定位原文：视频片段" })).toHaveAttribute(
      "href",
      "/youtube/summary/video-doc?start_ms=1200&end_ms=6400",
    );
    expect(screen.getByRole("link", { name: "定位原文：图像区域" }).getAttribute("href")).toContain(
      "/documents/image-doc/frames?frame=frame-8",
    );
  });

  it("keeps the review note and reloads the newer edge after a 409 conflict", async () => {
    const onReview = vi.fn().mockRejectedValue(new ApiError("conflict", 409));
    const onReload = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <EvidenceAuditDrawer
          open
          edge={edge}
          onClose={vi.fn()}
          onReview={onReview}
          onReload={onReload}
        />
      </MemoryRouter>,
    );
    const note = screen.getByLabelText("审核备注");
    fireEvent.change(note, { target: { value: "我已核对来源" } });
    fireEvent.click(screen.getByRole("button", { name: "确认关系" }));

    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));
    expect(note).toHaveValue("我已核对来源");
    expect(screen.getByText(/已有更新版本/)).toBeInTheDocument();
    expect(onReview).toHaveBeenCalledWith("confirm", 3, "我已核对来源");
  });
});
