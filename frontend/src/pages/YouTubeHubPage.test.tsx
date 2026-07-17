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

  it("submits manual summaries as durable background work and refreshes history", async () => {
    let historyCalls = 0;
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/youtube/summaries?")) {
        historyCalls += 1;
        return Response.json(
          historyCalls === 1
            ? []
            : [
                {
                  document_id: "",
                  video_id: "lvfh8QoSSYY",
                  title: "lvfh8QoSSYY",
                  channel_name: null,
                  thumbnail_url: null,
                  duration_sec: null,
                  published_at: null,
                  tldr: null,
                  tags: [],
                  created_at: "2026-07-17T00:00:00Z",
                  is_unread: false,
                  summary_status: "pending",
                  error: null,
                  failure_stage: "pending",
                  retryable: true,
                },
              ],
        );
      }
      if (url.endsWith("/youtube/summarize")) {
        return Response.json({
          video_id: "lvfh8QoSSYY",
          document_id: "",
          task_job_id: "job_yt_manual",
          status: "processing",
        });
      }
      if (url.includes("/youtube/summaries/by-video/")) {
        throw new Error("manual submit should not wait for foreground polling");
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.change(screen.getByPlaceholderText("https://www.youtube.com/watch?v=..."), {
      target: { value: "https://youtu.be/lvfh8QoSSYY?si=BRXEq898HCffeLMt" },
    });
    fireEvent.click(screen.getByRole("button", { name: /总\s*结/ }));

    expect(await screen.findByText("lvfh8QoSSYY")).toBeInTheDocument();
    expect(screen.getByText("待处理")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/youtube/summaries/by-video/"),
    );
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

  it("keeps broken thumbnails from exposing long title text in the history layout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/youtube/summaries?")) {
          return Response.json([
            {
              document_id: "doc_thumb",
              video_id: "thumb123",
              title:
                "台积电释放了什么信息？你的组合根本没有分散风险？跌麻了跌麻了，该听巴菲特讲课了！",
              channel_name: "投资频道",
              thumbnail_url: "https://i.ytimg.com/vi/thumb123/hqdefault.jpg",
              duration_sec: null,
              published_at: "2026-07-17T00:00:00Z",
              tldr: "本期视频分析半导体与投资风险。",
              tags: ["台积电"],
              created_at: "2026-07-17T00:00:00Z",
              is_unread: false,
              summary_status: "completed",
              error: null,
              failure_stage: null,
              retryable: false,
            },
          ]);
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    expect(await screen.findByText(/台积电释放了什么信息/)).toBeInTheDocument();
    const shell = screen.getByTestId("youtube-history-thumbnail-shell");
    const image = screen.getByTestId("youtube-history-thumbnail-image");

    expect(shell.style.width).toBe("96px");
    expect(shell.style.height).toBe("54px");
    expect(image).toHaveAttribute("alt", "");
    expect(image.getAttribute("src")).toBe(
      "/api/v1/youtube/videos/thumb123/thumbnail",
    );
  });
});
