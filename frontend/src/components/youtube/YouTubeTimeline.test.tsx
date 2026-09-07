import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { YouTubeTimeline } from "./YouTubeTimeline";
import { getYouTubeTimeline, retryVideo, type TimelinePage } from "../../services/youtubeApi";

vi.mock("../../services/youtubeApi", async () => {
  const actual = await vi.importActual<typeof import("../../services/youtubeApi")>(
    "../../services/youtubeApi",
  );
  return { ...actual, getYouTubeTimeline: vi.fn(), retryVideo: vi.fn() };
});

const timelinePage: TimelinePage = {
  items: [
    {
      document_id: "doc_done",
      video_id: "done",
      title: "已完成视频",
      channel_id: "channel_a",
      channel_name: "博主 A",
      thumbnail_url: null,
      duration_sec: 60,
      published_at: "2026-08-28T00:00:00Z",
      effective_time: "2026-08-28T00:00:00Z",
      time_source: "published_at",
      tldr: "已完成摘要",
      tags: ["AI"],
      created_at: "2026-08-28T00:00:00Z",
      is_unread: false,
      summary_status: "completed",
      error: null,
      failure_stage: null,
      retryable: false,
    },
    {
      document_id: "",
      video_id: "failed",
      title: "转写失败视频",
      channel_id: "channel_b",
      channel_name: "博主 B",
      thumbnail_url: null,
      duration_sec: null,
      published_at: "2026-08-27T00:00:00Z",
      effective_time: "2026-08-27T00:00:00Z",
      time_source: "published_at",
      tldr: null,
      tags: [],
      created_at: "2026-08-27T00:00:00Z",
      is_unread: false,
      summary_status: "failed",
      error: "asr: failed",
      failure_stage: "transcript",
      retryable: true,
    },
  ],
  next_cursor: null,
  channels: [
    { channel_id: "channel_a", channel_name: "博主 A", latest_effective_time: "2026-08-28T00:00:00Z", item_count: 1 },
    { channel_id: "channel_b", channel_name: "博主 B", latest_effective_time: "2026-08-27T00:00:00Z", item_count: 1 },
  ],
  months: [{ year_month: "2026-08", item_count: 2 }],
  total: 2,
  status_counts: { completed: 1, failed: 1 },
};

describe("YouTubeTimeline", () => {
  beforeEach(() => {
    vi.mocked(getYouTubeTimeline).mockResolvedValue(timelinePage);
    vi.mocked(retryVideo).mockResolvedValue({
      video_id: "failed",
      document_id: "",
      task_job_id: "job_retry",
      status: "processing",
    });
  });

  it("renders blogger lanes and all statuses", async () => {
    render(<YouTubeTimeline />, { wrapper: MemoryRouter });

    expect(await screen.findByText("博主 A")).toBeInTheDocument();
    expect(screen.getByText("博主 B")).toBeInTheDocument();
    expect(screen.getByText("已完成视频")).toBeInTheDocument();
    expect(screen.getByText("转写失败视频")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.getByText("转写失败")).toBeInTheDocument();
    expect(screen.getByText("asr: failed")).toBeInTheDocument();
    expect(screen.getByTestId("youtube-timeline-grid")).toHaveAttribute(
      "style",
      expect.stringContaining("display: grid"),
    );
    expect(screen.getByTestId("youtube-timeline-scroll")).toHaveAttribute(
      "style",
      expect.stringContaining("overflow: auto"),
    );
  });

  it("retries a failed card", async () => {
    render(<YouTubeTimeline />, { wrapper: MemoryRouter });
    fireEvent.click(await screen.findByRole("button", { name: "重新处理" }));

    await waitFor(() => expect(retryVideo).toHaveBeenCalledWith("failed", "ws_default"));
  });

  it("reloads the first page when a filter changes", async () => {
    render(<YouTubeTimeline />, { wrapper: MemoryRouter });
    await screen.findByText("已完成视频");
    fireEvent.mouseDown(screen.getByText("全部月份"));
    fireEvent.click(await screen.findByText("2026-08 (2)"));

    await waitFor(() =>
      expect(getYouTubeTimeline).toHaveBeenLastCalledWith(
        expect.objectContaining({ yearMonth: "2026-08", cursor: null }),
      ),
    );
  });

  it("uses a stable unknown-channel key for filtering", async () => {
    vi.mocked(getYouTubeTimeline).mockResolvedValue({
      ...timelinePage,
      items: [
        {
          ...timelinePage.items[0],
          video_id: "unknown",
          channel_id: null,
          channel_name: "未识别博主",
        },
      ],
      channels: [
        {
          channel_id: null,
          channel_name: "未识别博主",
          latest_effective_time: "2026-08-28T00:00:00Z",
          item_count: 1,
        },
      ],
    });
    render(<YouTubeTimeline />, { wrapper: MemoryRouter });
    await screen.findByText("未识别博主");

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "博主筛选" }));
    const labels = await screen.findAllByText("未识别博主");
    fireEvent.click(labels.at(-1)!);

    await waitFor(() =>
      expect(getYouTubeTimeline).toHaveBeenLastCalledWith(
        expect.objectContaining({ channelId: "__unknown__", cursor: null }),
      ),
    );
  });

  it("keeps same-named channels in distinct lanes without duplicating cards", async () => {
    vi.mocked(getYouTubeTimeline).mockResolvedValue({
      ...timelinePage,
      items: [
        {
          ...timelinePage.items[0],
          video_id: "same_name_a",
          title: "频道 A 视频",
          channel_id: "channel_a",
          channel_name: "同名博主",
        },
        {
          ...timelinePage.items[0],
          video_id: "same_name_b",
          title: "频道 B 视频",
          channel_id: "channel_b",
          channel_name: "同名博主",
        },
      ],
      channels: [
        { channel_id: "channel_a", channel_name: "同名博主", latest_effective_time: "2026-08-28T00:00:00Z", item_count: 1 },
        { channel_id: "channel_b", channel_name: "同名博主", latest_effective_time: "2026-08-28T00:00:00Z", item_count: 1 },
      ],
    });

    render(<YouTubeTimeline />, { wrapper: MemoryRouter });

    expect(await screen.findAllByText("频道 A 视频")).toHaveLength(1);
    expect(screen.getAllByText("频道 B 视频")).toHaveLength(1);
  });

  it("uses one UTC date label and marks created-at fallback as platform time", async () => {
    vi.mocked(getYouTubeTimeline).mockResolvedValue({
      ...timelinePage,
      items: [
        {
          ...timelinePage.items[0],
          effective_time: "2026-08-31T17:00:00Z",
          time_source: "created_at",
        },
      ],
    });

    render(<YouTubeTimeline />, { wrapper: MemoryRouter });

    expect(await screen.findByText("2026-08-31 · 平台时间")).toBeInTheDocument();
  });

  it("shows the matching lane when a filter returns a channel outside the default six", async () => {
    const channels = [
      ...timelinePage.channels,
      ...Array.from({ length: 5 }, (_, index) => ({
        channel_id: `channel_${index + 3}`,
        channel_name: `博主 ${index + 3}`,
        latest_effective_time: `2026-08-${String(26 - index).padStart(2, "0")}T00:00:00Z`,
        item_count: 1,
      })),
    ];
    const filteredPage: TimelinePage = {
      ...timelinePage,
      items: [
        {
          ...timelinePage.items[0],
          video_id: "filtered_channel_7",
          title: "第七博主的筛选结果",
          channel_id: "channel_7",
          channel_name: "博主 7",
        },
      ],
      channels,
      total: 1,
    };
    vi.mocked(getYouTubeTimeline)
      .mockReset()
      .mockResolvedValueOnce({ ...timelinePage, channels })
      .mockResolvedValue(filteredPage);

    render(<YouTubeTimeline />, { wrapper: MemoryRouter });
    await screen.findByText("已完成视频");
    fireEvent.mouseDown(screen.getByText("全部月份"));
    fireEvent.click(await screen.findByText("2026-08 (2)"));

    expect(await screen.findByText("第七博主的筛选结果")).toBeInTheDocument();
    expect(screen.getByText("博主 7")).toBeInTheDocument();
  });
});
