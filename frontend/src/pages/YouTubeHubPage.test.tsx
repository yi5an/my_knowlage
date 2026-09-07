import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { YouTubeHubPage } from "./YouTubeHubPage";
import type { TimelineItem, TimelinePage } from "../services/youtubeApi";

const completedItem: TimelineItem = {
  document_id: "doc_ai",
  video_id: "ai123",
  title: "英伟达 GB300 供应链更新",
  channel_id: "channel_ai",
  channel_name: "AI 投资频道",
  thumbnail_url: null,
  duration_sec: 1280,
  published_at: "2026-08-28T00:00:00Z",
  effective_time: "2026-08-28T00:00:00Z",
  time_source: "published_at",
  tldr: "本期跟踪 AI 算力供应链与英伟达新品节奏。",
  tags: ["AI算力", "NVDA"],
  created_at: "2026-08-28T00:00:00Z",
  is_unread: false,
  summary_status: "completed",
  error: null,
  failure_stage: null,
  retryable: false,
};

function timelineResponse(items: TimelineItem[] = [completedItem]): TimelinePage {
  return {
    items,
    next_cursor: null,
    channels: items.map((item) => ({
      channel_id: item.channel_id,
      channel_name: item.channel_name,
      latest_effective_time: item.effective_time,
      item_count: 1,
    })),
    months: [{ year_month: "2026-08", item_count: items.length }],
    total: items.length,
    status_counts: { completed: items.length },
  };
}

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

  it("renders the history timeline with blogger lanes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/youtube/timeline?")) return Response.json(timelineResponse());
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderPage();

    expect(await screen.findByText("AI 投资频道")).toBeInTheDocument();
    expect(screen.getByText("英伟达 GB300 供应链更新")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
  });

  it("submits a manual summary and refreshes the timeline", async () => {
    let timelineCalls = 0;
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/youtube/timeline?")) {
        timelineCalls += 1;
        const item = {
          ...completedItem,
          video_id: "lvfh8QoSSYY",
          document_id: "",
          title: "lvfh8QoSSYY",
          summary_status: "processing",
          tldr: null,
          tags: [],
          retryable: true,
        };
        return Response.json(timelineResponse(timelineCalls > 1 ? [item] : []));
      }
      if (url.endsWith("/youtube/summarize")) {
        return Response.json({
          video_id: "lvfh8QoSSYY",
          document_id: "",
          task_job_id: "job_yt_manual",
          status: "processing",
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    await waitFor(() => expect(timelineCalls).toBe(1));
    fireEvent.change(screen.getByPlaceholderText("https://www.youtube.com/watch?v=..."), {
      target: { value: "https://youtu.be/lvfh8QoSSYY" },
    });
    fireEvent.click(screen.getByRole("button", { name: /总\s*结/ }));

    expect(await screen.findByText("lvfh8QoSSYY")).toBeInTheDocument();
    expect(await screen.findByText("处理中")).toBeInTheDocument();
    expect(timelineCalls).toBeGreaterThanOrEqual(2);
  });

  it("ignores a scheduled livestream without refreshing the timeline", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/youtube/timeline?")) return Response.json(timelineResponse([]));
      if (url.endsWith("/youtube/summarize")) {
        return Response.json({ video_id: "upcoming123", document_id: "", task_job_id: "", status: "ignored_live" });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/youtube/timeline?")).length).toBe(1));
    fireEvent.change(screen.getByPlaceholderText("https://www.youtube.com/watch?v=..."), {
      target: { value: "https://youtu.be/upcoming123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /总\s*结/ }));

    expect(await screen.findByText("已忽略直播或预约直播，不会创建总结任务。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/youtube/timeline?")).length).toBe(1);
  });
});
