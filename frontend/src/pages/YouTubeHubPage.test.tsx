import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("groups history cards by topic and filters by channel", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/youtube/summaries?")) {
          return Response.json([
            {
              document_id: "doc_ai",
              video_id: "ai123",
              title: "英伟达 GB300 供应链更新",
              channel_name: "AI 投资频道",
              thumbnail_url: "https://i.ytimg.com/vi/ai123/hqdefault.jpg",
              duration_sec: 1280,
              published_at: "2026-07-17T00:00:00Z",
              tldr: "本期跟踪 AI 算力供应链与英伟达新品节奏。",
              tags: ["AI算力", "NVDA"],
              created_at: "2026-07-17T00:00:00Z",
              is_unread: false,
              summary_status: "completed",
              error: null,
              failure_stage: null,
              retryable: false,
            },
            {
              document_id: "doc_macro",
              video_id: "macro123",
              title: "美联储降息路径更新",
              channel_name: "宏观研究所",
              thumbnail_url: null,
              duration_sec: 900,
              published_at: "2026-07-16T00:00:00Z",
              tldr: "本期讨论通胀、就业与美元流动性。",
              tags: ["宏观", "美联储"],
              created_at: "2026-07-16T00:00:00Z",
              is_unread: false,
              summary_status: "completed",
              error: null,
              failure_stage: null,
              retryable: false,
            },
            {
              document_id: "doc_ai_2",
              video_id: "ai456",
              title: "光模块订单继续上修",
              channel_name: "AI 投资频道",
              thumbnail_url: null,
              duration_sec: 720,
              published_at: "2026-07-15T00:00:00Z",
              tldr: "光模块厂商订单和交付周期继续改善。",
              tags: ["AI算力", "光模块"],
              created_at: "2026-07-15T00:00:00Z",
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

    expect(await screen.findByRole("heading", { name: "AI算力" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "宏观" })).toBeInTheDocument();
    expect(screen.getByText("英伟达 GB300 供应链更新")).toBeInTheDocument();
    expect(screen.getByText("美联储降息路径更新")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("博主筛选"), {
      target: { value: "宏观研究所" },
    });

    await waitFor(() => {
      expect(screen.queryByText("英伟达 GB300 供应链更新")).not.toBeInTheDocument();
    });
    expect(screen.getByText("美联储降息路径更新")).toBeInTheDocument();
    expect(screen.queryByText("AI算力")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "宏观" })).toBeInTheDocument();
  });

  it("renders a topic index that links to history sections", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/youtube/summaries?")) {
          return Response.json([
            {
              document_id: "doc_ai_index",
              video_id: "aiindex",
              title: "AI 算力更新",
              channel_name: "AI 投资频道",
              thumbnail_url: null,
              duration_sec: 1280,
              published_at: "2026-07-17T00:00:00Z",
              tldr: "AI 算力供应链更新。",
              tags: ["AI算力", "NVDA"],
              created_at: "2026-07-17T00:00:00Z",
              is_unread: false,
              summary_status: "completed",
              error: null,
              failure_stage: null,
              retryable: false,
            },
            {
              document_id: "doc_macro_index",
              video_id: "macroindex",
              title: "宏观流动性更新",
              channel_name: "宏观研究所",
              thumbnail_url: null,
              duration_sec: 900,
              published_at: "2026-07-16T00:00:00Z",
              tldr: "宏观流动性和美联储路径更新。",
              tags: ["宏观", "美联储"],
              created_at: "2026-07-16T00:00:00Z",
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

    const topicIndex = await screen.findByRole("navigation", { name: "主题索引" });
    expect(topicIndex).toBeInTheDocument();
    const aiIndexLink = within(topicIndex).getByRole("link", { name: /AI算力/ });
    const macroIndexLink = within(topicIndex).getByRole("link", { name: /宏观/ });

    expect(aiIndexLink).toHaveAttribute("href", "#youtube-topic-0");
    expect(macroIndexLink).toHaveAttribute("href", "#youtube-topic-1");
    expect(document.getElementById("youtube-topic-0")).toHaveTextContent("AI算力");
    expect(document.getElementById("youtube-topic-1")).toHaveTextContent("宏观");
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

  it("reports an ignored scheduled livestream without refreshing history", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/youtube/summaries?")) return Response.json([]);
      if (url.endsWith("/youtube/summarize")) {
        return Response.json({
          video_id: "upcoming123",
          document_id: "",
          task_job_id: "",
          status: "ignored_live",
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.change(screen.getByPlaceholderText("https://www.youtube.com/watch?v=..."), {
      target: { value: "https://youtu.be/upcoming123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /总\s*结/ }));

    expect(
      await screen.findByText("已忽略直播或预约直播，不会创建总结任务。"),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/youtube/summaries?"))).toHaveLength(
      1,
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

    const title = screen.getByTestId("youtube-history-card-title");
    expect(title.style.overflowWrap).toBe("anywhere");
    expect(title.style.wordBreak).toBe("break-word");
  });
});
