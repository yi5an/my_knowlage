import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { YouTubeHubPage } from "./YouTubeHubPage";

function renderPage() {
  render(
    <MemoryRouter>
      <YouTubeHubPage />
    </MemoryRouter>,
  );
}

describe("YouTubeHubPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps failed video records visible in history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/youtube/summaries?")) {
          return Response.json([
            {
              document_id: "",
              video_id: "failed123",
              title: "Failed before document",
              channel_name: "AI Channel",
              thumbnail_url: null,
              duration_sec: null,
              published_at: "2026-07-02T00:00:00Z",
              tldr: null,
              tags: [],
              created_at: "2026-07-03T00:00:00Z",
              is_unread: false,
              summary_status: "failed",
              error: "asr: empty transcription",
              failure_stage: "transcript",
              retryable: true,
            },
          ]);
        }
        if (url.includes("/youtube/videos/failed123/retry")) {
          return Response.json({
            video_id: "failed123",
            document_id: "",
            task_job_id: "retry_failed123",
            status: "processing",
          });
        }
        if (url.includes("/youtube/summaries/by-video/failed123")) {
          return Response.json({ video_id: "failed123", status: "processing" });
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    expect(await screen.findByText("Failed before document")).toBeInTheDocument();
    expect(screen.getByText("转写失败")).toBeInTheDocument();
    expect(screen.getByText("asr: empty transcription")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重新处理" }));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/youtube/videos/failed123/retry"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("marks members-only videos as 无访问权限 with no retry button", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/youtube/summaries?")) {
          return Response.json([
            {
              document_id: "",
              video_id: "members123",
              title: "Members-only talk",
              channel_name: "Paywall Channel",
              thumbnail_url: null,
              duration_sec: null,
              published_at: "2026-07-02T00:00:00Z",
              tldr: null,
              tags: [],
              created_at: "2026-07-03T00:00:00Z",
              is_unread: false,
              summary_status: "access_denied",
              error: "access denied: Join this channel to get access",
              failure_stage: null,
              retryable: false,
            },
          ]);
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    expect(await screen.findByText("Members-only talk")).toBeInTheDocument();
    expect(screen.getByText("无访问权限")).toBeInTheDocument();
    // No retry button for a permanently-blocked video.
    expect(screen.queryByRole("button", { name: "重新处理" })).not.toBeInTheDocument();
  });
});
