import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VideoSummaryPage } from "./VideoSummaryPage";

const summaryCard = {
  document_id: "doc_yt_1",
  video_id: "dQw4w9WgXcQ",
  title: "GPT-5 Deep Dive",
  channel_name: "AI Channel",
  duration_sec: 60,
  published_at: "2026-01-01T00:00:00Z",
  thumbnail_url: null,
  knowledge_base_imported: false,
  summary: {
    tldr: "A concise overview.",
    key_points: [{ point: "Big point", timestamp: 10, timestamp_str: "00:10" }],
    quotes: [],
    chapters: [],
    tags: ["AI"],
    transcript_source: "manual",
  },
  mindmap: null,
  transcript: "Transcript text",
};

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/youtube/summaries/doc_yt_1"]}>
      <Routes>
        <Route path="/youtube/summaries/:documentId" element={<VideoSummaryPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("VideoSummaryPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lets the user manually import a summary into the knowledge base", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (
        url.endsWith("/youtube/summaries/doc_yt_1") &&
        (init?.method ?? "GET") === "GET"
      ) {
        return Response.json(summaryCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/import-to-knowledge-base")) {
        return Response.json({ ...summaryCard, knowledge_base_imported: true });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    const importButton = await screen.findByRole("button", { name: /加入知识库/ });
    fireEvent.click(importButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/youtube/summaries/doc_yt_1/import-to-knowledge-base",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect((await screen.findAllByText("已加入知识库")).length).toBeGreaterThan(0);
  });
});
