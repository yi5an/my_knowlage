import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanionDrawer } from "./CompanionDrawer";
import { CompanionProvider } from "./CompanionProvider";

describe("CompanionDrawer", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/companion/sessions")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: "session_1",
                workspace_id: "ws",
                subject_type: "youtube_video",
                subject_id: "video_1",
                title: "Video title",
                status: "active",
              }),
              { status: 200 },
            ),
          );
        }
        if (url.endsWith("/messages") && init?.method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: "message_2",
                role: "assistant",
                content: "平台内佐证显示该判断仍需复核。",
                citations: [
                  {
                    source_id: "chunk_1",
                    source_title: "Video title",
                    excerpt: "GPU 需求增长",
                    relation: "primary",
                    confidence: 0.8,
                  },
                ],
                confidence: 0.8,
              }),
              { status: 200 },
            ),
          );
        }
        if (url.endsWith("/session_1")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: "session_1",
                workspace_id: "ws",
                subject_type: "youtube_video",
                subject_id: "video_1",
                title: "Video title",
                status: "active",
                messages: [],
                insights: [],
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({ task_job_id: "task_1", status: "pending" }), { status: 202 }));
      }),
    );
  });

  it("opens with the active video context and sends a saved question", async () => {
    render(
      <CompanionProvider
        initialContext={{
          workspaceId: "ws",
          subjectType: "youtube_video",
          subjectId: "video_1",
          title: "Video title",
        }}
      >
        <CompanionDrawer />
      </CompanionProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "AI 陪读" }));
    expect(await screen.findByText("视频：Video title")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("围绕当前内容提问…"), {
      target: { value: "有哪些反证？" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("平台内佐证显示该判断仍需复核。"))
      .toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
  });
});
