import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubscriptionPage } from "./SubscriptionPage";

describe("SubscriptionPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows real summary status for videos discovered by subscription polling", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/youtube/subscriptions")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (u.includes("/youtube/poll") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            poll_count: 8,
            discovered: 2,
            videos: [
              { video_id: "failed123", title: "失败的视频", channel_id: "UC_failed" },
              { video_id: "done123", title: "完成的视频", channel_id: "UC_done" },
            ],
          }),
          { status: 200 },
        );
      }
      if (u.includes("/youtube/summaries/by-video/failed123")) {
        return new Response(
          JSON.stringify({
            video_id: "failed123",
            status: "failed",
            error: "summary interrupted by backend restart; please retry processing",
          }),
          { status: 200 },
        );
      }
      if (u.includes("/youtube/summaries/by-video/done123")) {
        return new Response(
          JSON.stringify({
            video_id: "done123",
            status: "succeeded",
            document_id: "doc_done",
          }),
          { status: 200 },
        );
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SubscriptionPage />);

    fireEvent.click(await screen.findByRole("button", { name: /立即轮询/ }));

    expect(await screen.findByText("检查 8 个频道，发现 2 个新视频。")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("已完成 1")).toBeInTheDocument();
      expect(screen.getByText("失败 1")).toBeInTheDocument();
      expect(screen.getByText("处理中 0")).toBeInTheDocument();
    });
    expect(screen.getByText("失败的视频")).toBeInTheDocument();
    expect(screen.getByText("完成的视频")).toBeInTheDocument();
    expect(
      screen.getByText("summary interrupted by backend restart; please retry processing"),
    ).toBeInTheDocument();
  });
});
