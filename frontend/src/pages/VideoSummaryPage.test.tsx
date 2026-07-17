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
  visual_frames: [],
  local_video_status: "not_downloaded",
  local_video_url: null,
  local_video_size: null,
  local_video_error: null,
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

  it("renders visual OCR evidence when frames are available", async () => {
    const visualCard = {
      ...summaryCard,
      visual_frames: [
        {
          id: "vfa_1",
          timestamp_sec: 30,
          timestamp_str: "00:30",
          image_path: "/storage/youtube_frames/demo/frame_0001.jpg",
          image_url: null,
          frame_type: "mindmap",
          ocr_text: "行业轮动思维导图\n美元流动性 -> 风险资产",
          ocr_blocks: [],
          structured_notes: {
            title: "行业轮动思维导图",
            bullets: ["美元流动性 -> 风险资产"],
          },
          confidence: 0.95,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(visualCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "视觉资料" }));

    expect((await screen.findAllByText("行业轮动思维导图")).length).toBeGreaterThan(0);
    expect(screen.getByText("美元流动性 -> 风险资产")).toBeInTheDocument();
    expect(screen.getByText("[00:30 ↗]")).toBeInTheDocument();
  });

  it("renders possible upstream source traces", async () => {
    const tracedCard = {
      ...summaryCard,
      source_traces: [
        {
          source_item_id: "inv_x_trace",
          source_title: "@nvidia: AI data center capex remains strong",
          source_name: "@nvidia",
          source_url: "https://x.com/nvidia/status/1",
          published_at: "2026-07-15T08:00:00Z",
          matched_fact: "AI data center capex remains strong.",
          evidence_excerpt: "AI data center capex remains strong",
          lead_time_hours: 4,
          confidence: 0.91,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(tracedCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("可能信息来源")).toBeInTheDocument();
    expect(screen.getByText("@nvidia: AI data center capex remains strong")).toBeInTheDocument();
    expect(screen.getByText("领先 4h")).toBeInTheDocument();
    expect(screen.getByText("匹配事实：AI data center capex remains strong.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开原始来源" })).toHaveAttribute(
      "href",
      "https://x.com/nvidia/status/1",
    );
  });

  it("can re-enqueue a failed local video download from the summary page", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json({
          ...summaryCard,
          local_video_status: "failed",
          local_video_error: "yt-dlp failed",
        });
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      if (
        url.endsWith("/youtube/videos/dQw4w9WgXcQ/local-video/download") &&
        init?.method === "POST"
      ) {
        return Response.json({
          video_id: "dQw4w9WgXcQ",
          status: "queued",
          task_job_id: "job_yt_video_download_1",
          local_video_url: null,
          local_video_size: null,
          error: null,
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    const downloadButton = await screen.findByRole("button", { name: "重新下载到 NAS" });
    fireEvent.click(downloadButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/youtube/videos/dQw4w9WgXcQ/local-video/download",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(await screen.findByText("下载已加入队列")).toBeInTheDocument();
  });

  it("shows automatic local video download status before the file is ready", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(summaryCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("等待自动下载到 NAS")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载到 NAS" })).not.toBeInTheDocument();
  });

  it("renders the local video player when the video has been downloaded", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json({
          ...summaryCard,
          local_video_status: "downloaded",
          local_video_url: "/api/v1/youtube/videos/dQw4w9WgXcQ/local-video",
          local_video_size: 1024,
        });
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    const player = await screen.findByTestId("youtube-local-video-player");
    expect(player).toHaveAttribute(
      "src",
      "/api/v1/youtube/videos/dQw4w9WgXcQ/local-video",
    );
  });

  it("cleans noisy visual OCR notes and hides duplicate raw text by default", async () => {
    const rawOcr = [
      "大摩|周期论剑",
      "(07.08)",
      "行业商业化落地，国内企业实现盈亏平衡",
      "<",
      "长期驱动：人力替代、老龄化、AI技术迭代",
      "汽车行业-RobotaxiO",
      "运营区域扩张、发放自动驾驶牌照",
      "短期股价催化",
      "量产车型落地、市场体验改善提振情绪",
      "投资成果：30只全产业链相关股票组合",
      "核心结论：中短期保费不会大幅下滑",
      "车险分阶段演变",
      "L2L3：现有车险框架保留，新增系统算法责任险，保费或上行",
      "L4普及：三者险萎缩，车损转为资产保障，算法险成核心险种",
      "保险行业-自动驾驶对车险影响",
      "行业规模预判",
    ].join("\n");
    const visualCard = {
      ...summaryCard,
      visual_frames: [
        {
          id: "vfa_1",
          timestamp_sec: 0,
          timestamp_str: "00:00",
          image_path: "/storage/youtube_frames/demo/frame_0001.jpg",
          image_url: null,
          frame_type: "table",
          ocr_text: rawOcr,
          ocr_blocks: [],
          structured_notes: {
            title: "大摩|周期论剑",
            bullets: rawOcr.split("\n").slice(1),
          },
          confidence: 0.95,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(visualCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "视觉资料" }));

    expect((await screen.findAllByText("大摩|周期论剑")).length).toBeGreaterThan(0);
    expect(screen.queryByText("<")).not.toBeInTheDocument();
    expect(screen.queryByText(rawOcr)).not.toBeInTheDocument();
    expect(screen.getByText("行业规模预判")).toBeInTheDocument();
    expect(screen.getByText("展开查看原始 OCR")).toBeInTheDocument();
    expect(screen.queryByText(/还有 \d+ 条/)).not.toBeInTheDocument();
  });

  it("opens visual frame images and renders OCR notes as a line-based mindmap", async () => {
    const visualCard = {
      ...summaryCard,
      visual_frames: [
        {
          id: "vfa_1",
          timestamp_sec: 0,
          timestamp_str: "00:00",
          image_path: "/storage/youtube_frames/demo/frame_0001.jpg",
          image_url: "/api/v1/youtube/visual-frames/vfa_1/image",
          frame_type: "mindmap",
          ocr_text: "大摩|周期论剑\n报告发布背景\n中美为核心市场\n短期股价催化\n量产车型落地",
          ocr_blocks: [],
          structured_notes: {
            title: "大摩|周期论剑",
            bullets: [
              "报告发布背景",
              "中美为核心市场",
              "短期股价催化",
              "量产车型落地",
            ],
          },
          confidence: 0.95,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(visualCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "视觉资料" }));

    const imageLink = await screen.findByRole("link", { name: "打开视觉资料图片" });
    expect(imageLink).toHaveAttribute(
      "href",
      "/api/v1/youtube/visual-frames/vfa_1/image",
    );
    expect(screen.getByRole("tree", { name: "视觉资料脑图" })).toBeInTheDocument();
    expect(screen.getByText("报告发布背景")).toBeInTheDocument();
    expect(screen.getByTestId("visual-mindmap-root")).toHaveTextContent("大摩|周期论剑");
    expect(screen.getByTestId("visual-mindmap-branches")).toBeInTheDocument();
    expect(screen.getByTestId("visual-mindmap-canvas")).toBeInTheDocument();
    expect(screen.getAllByTestId("visual-mindmap-curve").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByTestId("visual-mindmap-dot").length).toBeGreaterThanOrEqual(4);
    expect(screen.getAllByTestId("visual-mindmap-node").length).toBeGreaterThanOrEqual(4);
    expect(screen.getAllByTestId("visual-mindmap-leaf").length).toBeGreaterThanOrEqual(2);
  });

  it("prefers structured visual mindmap trees over flat OCR bullets", async () => {
    const visualCard = {
      ...summaryCard,
      visual_frames: [
        {
          id: "vfa_1",
          timestamp_sec: 0,
          timestamp_str: "00:00",
          image_path: "/storage/youtube_frames/demo/frame_0001.jpg",
          image_url: "/api/v1/youtube/visual-frames/vfa_1/image",
          frame_type: "mindmap",
          ocr_text: "大摩|周期论剑",
          ocr_blocks: [],
          structured_notes: {
            title: "大摩|周期论剑",
            bullets: [],
            tree: {
              title: "大摩|周期论剑",
              children: [
                {
                  title: "汽车行业-Robotaxi",
                  children: [
                    {
                      title: "报告发布背景",
                      children: [
                        { title: "中美为核心市场、出海中东、欧洲", children: [] },
                      ],
                    },
                  ],
                },
              ],
            },
          },
          confidence: 0.95,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(visualCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "视觉资料" }));

    expect(await screen.findByRole("tree", { name: "视觉资料脑图" })).toBeInTheDocument();
    expect(screen.getByText("汽车行业-Robotaxi")).toBeInTheDocument();
    expect(screen.getByText("报告发布背景")).toBeInTheDocument();
    expect(screen.getByText("中美为核心市场、出海中东、欧洲")).toBeInTheDocument();
    expect(screen.getByText("报告发布背景").closest("[aria-level='3']")).toBeTruthy();
    expect(screen.getByText("中美为核心市场、出海中东、欧洲").closest("[aria-level='4']")).toBeTruthy();
  });

  it("edits and saves visual mindmap nodes", async () => {
    const visualCard = {
      ...summaryCard,
      visual_frames: [
        {
          id: "vfa_1",
          timestamp_sec: 0,
          timestamp_str: "00:00",
          image_path: "/storage/youtube_frames/demo/frame_0001.jpg",
          image_url: "/api/v1/youtube/visual-frames/vfa_1/image",
          frame_type: "mindmap",
          ocr_text: "大摩|周期论剑",
          ocr_blocks: [],
          structured_notes: {
            title: "大摩|周期论剑",
            bullets: [],
            tree: {
              title: "大摩|周期论剑",
              children: [
                {
                  title: "汽车行业-Robotaxi",
                  children: [
                    { title: "报告发布背景", children: [] },
                  ],
                },
              ],
            },
          },
          confidence: 0.95,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (
        url.endsWith("/youtube/summaries/doc_yt_1") &&
        (init?.method ?? "GET") === "GET"
      ) {
        return Response.json(visualCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      if (url.endsWith("/youtube/visual-frames/vfa_1/mindmap")) {
        return Response.json({
          ...visualCard.visual_frames[0],
          structured_notes: {
            ...visualCard.visual_frames[0].structured_notes,
            tree: JSON.parse(String(init?.body)).tree,
          },
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "视觉资料" }));
    fireEvent.click(await screen.findByRole("button", { name: /编辑脑图/ }));
    fireEvent.click(screen.getByDisplayValue("报告发布背景"));
    fireEvent.click(screen.getByRole("button", { name: /新增子节点/ }));
    fireEvent.change(screen.getByDisplayValue("新节点"), {
      target: { value: "商业化落地" },
    });
    fireEvent.click(screen.getByRole("button", { name: /保存脑图/ }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([url]) =>
        String(url).endsWith("/youtube/visual-frames/vfa_1/mindmap"),
      );
      expect(saveCall).toBeTruthy();
      const [, init] = saveCall as [string, RequestInit];
      expect(init.method).toBe("PUT");
      const payload = JSON.parse(String(init.body));
      expect(payload.tree.title).toBe("大摩|周期论剑");
      expect(payload.tree.children[0].children[0].children[0].title).toBe(
        "商业化落地",
      );
    });
    expect(await screen.findByText("商业化落地")).toBeInTheDocument();
  });

  it("groups visual OCR lines under section branches instead of repeated summaries", async () => {
    const visualCard = {
      ...summaryCard,
      visual_frames: [
        {
          id: "vfa_1",
          timestamp_sec: 0,
          timestamp_str: "00:00",
          image_path: "/storage/youtube_frames/demo/frame_0001.jpg",
          image_url: "/api/v1/youtube/visual-frames/vfa_1/image",
          frame_type: "table",
          ocr_text: "大摩|周期论剑\n报告发布背景\n中美为核心市场\n赛道参与者分层清晰\n长期驱动\n人力替代、老龄化、AI技术迭代\n汽车行业-RobotaxiO\n运营区域扩张、发放自动驾驶牌照",
          ocr_blocks: [],
          structured_notes: {
            title: "大摩|周期论剑",
            bullets: [
              "报告发布背景",
              "中美为核心市场",
              "赛道参与者分层清晰",
              "长期驱动",
              "人力替代、老龄化、AI技术迭代",
              "汽车行业-RobotaxiO",
              "运营区域扩张、发放自动驾驶牌照",
            ],
          },
          confidence: 0.95,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(visualCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "视觉资料" }));

    expect(await screen.findByText("报告发布背景")).toBeInTheDocument();
    expect(screen.getByText("中美为核心市场")).toBeInTheDocument();
    expect(screen.getByText("运营区域扩张、发放自动驾驶牌照")).toBeInTheDocument();
    expect(screen.queryAllByText("核心摘要")).toHaveLength(0);
  });

  it("renders the complete visual OCR mindmap instead of truncating to the first screenful", async () => {
    const lines = [
      "大摩|周期论剑",
      "报告发布背景",
      "中美为核心市场",
      "赛道参与者分层清晰",
      "长期驱动",
      "人力替代、老龄化、AI技术迭代",
      "汽车行业-RobotaxiO",
      "运营区域扩张、发放自动驾驶牌照",
      "短期股价催化",
      "量产车型落地、市场体验改善提振情绪",
      "投资成果",
      "30只全产业链相关股票组合",
      "核心结论",
      "中短期保费不会大幅下滑",
      "车险分阶段演变",
      "L2L3：现有车险框架保留，新增系统算法责任险，保费或上行",
      "L4普及：三者险萎缩，车损转为资产保障，算法险成核心险种",
      "保险行业-自动驾驶对车险影响",
      "行业规模预判",
      "2030年前保费小个位数增长，规模破万亿",
      "2035年后保费见顶回落，新增险种对冲下滑",
    ];
    const visualCard = {
      ...summaryCard,
      visual_frames: [
        {
          id: "vfa_1",
          timestamp_sec: 0,
          timestamp_str: "00:00",
          image_path: "/storage/youtube_frames/demo/frame_0001.jpg",
          image_url: "/api/v1/youtube/visual-frames/vfa_1/image",
          frame_type: "table",
          ocr_text: lines.join("\n"),
          ocr_blocks: [],
          structured_notes: {
            title: lines[0],
            bullets: lines.slice(1),
          },
          confidence: 0.95,
        },
      ],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/youtube/summaries/doc_yt_1")) {
        return Response.json(visualCard);
      }
      if (url.endsWith("/youtube/summaries/doc_yt_1/mark-read")) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("tab", { name: "视觉资料" }));

    expect(await screen.findByText("报告发布背景")).toBeInTheDocument();
    expect(screen.getByText("2035年后保费见顶回落，新增险种对冲下滑")).toBeInTheDocument();
    expect(screen.queryByText(/还有 \d+ 条/)).not.toBeInTheDocument();
  });
});
