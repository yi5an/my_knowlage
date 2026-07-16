import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvestmentDashboardPage } from "./InvestmentDashboardPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentDashboardPage />
    </MemoryRouter>,
  );
}

describe("InvestmentDashboardPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/dashboard")) {
          return new Response(
            JSON.stringify({
              pending_review_count: 3,
              pending_claims_count: 1,
              theses_challenged_count: 0,
              today_primary_count: 2,
              today_macro_count: 1,
              untranslated_count: 4,
              unextracted_count: 3,
              unsignaled_count: 2,
              failed_job_count: 1,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (u.includes("/investment/digest")) {
          return new Response(
            JSON.stringify({
              counts: {
                pending_review_count: 0,
                pending_claims_count: 0,
                theses_challenged_count: 0,
                today_primary_count: 0,
                today_macro_count: 0,
                untranslated_count: 0,
                unextracted_count: 0,
                unsignaled_count: 0,
                failed_job_count: 0,
              },
              today_highlights: [],
              pending_claims: [],
              challenged_items: [],
              early_signals: [],
              pending_facts: [],
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/items")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/signals")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the page heading", async () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "投资工作台" })).toBeInTheDocument();
  });

  it("shows real dashboard counts from the API (no sample data)", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("今日待处理")).toBeInTheDocument();
    });
    expect(metricCard("今日待处理")).toHaveTextContent("3");
    expect(metricCard("待翻译")).toHaveTextContent("4");
    expect(metricCard("待抽取事实")).toHaveTextContent("3");
    expect(metricCard("待生成信号")).toHaveTextContent("2");
    expect(metricCard("失败任务")).toHaveTextContent("1");
  });

  it("shows an empty state for pending items when the list is empty", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("暂无待处理信息")).toBeInTheDocument();
    });
  });

  it("shows timestamps for pending investment items", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/dashboard")) {
          return new Response(
            JSON.stringify({
              pending_review_count: 1,
              pending_claims_count: 0,
              theses_challenged_count: 0,
              today_primary_count: 0,
              today_macro_count: 0,
              untranslated_count: 0,
              unextracted_count: 0,
              unsignaled_count: 0,
              failed_job_count: 0,
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/digest")) {
          return new Response(
            JSON.stringify({
              counts: {
                pending_review_count: 0,
                pending_claims_count: 0,
                theses_challenged_count: 0,
                today_primary_count: 0,
                today_macro_count: 0,
                untranslated_count: 0,
                unextracted_count: 0,
                unsignaled_count: 0,
                failed_job_count: 0,
              },
              today_highlights: [],
              pending_claims: [],
              challenged_items: [],
              early_signals: [],
              pending_facts: [],
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "item_x",
                workspace_id: "ws_default",
                dedupe_key: "item_x",
                title: "NVIDIA launches new AI system",
                title_zh: "英伟达发布新的 AI 系统",
                info_layer: "opinion",
                source_credibility: "analyst",
                importance: "medium",
                impact_direction: "positive",
                impact_horizon: "short",
                thesis_impact: "supports",
                action_status: "pending_review",
                source_name: "X / NVIDIA",
                published_at: "2026-07-16T09:30:00Z",
                summary: "图片文字：\nGB300 NVL72 rack-scale AI system ships to partners.",
                attachments: [
                  {
                    title: "X 图片 1",
                    url: "https://pbs.twimg.com/media/example.jpg",
                    content_type: "image",
                    text_excerpt: "GB300 NVL72 rack-scale AI system ships to partners.",
                  },
                ],
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/signals")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByText("英伟达发布新的 AI 系统")).toBeInTheDocument();
    expect(screen.getByText("发布时间 07-16 17:30")).toBeInTheDocument();
    expect(screen.getByText(/GB300 NVL72 rack-scale AI system/)).toBeInTheDocument();
    expect(screen.getByText("图片 1")).toBeInTheDocument();
  });

  it("shows early signals from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/dashboard")) {
          return new Response(
            JSON.stringify({
              pending_review_count: 0,
              pending_claims_count: 0,
              theses_challenged_count: 0,
              today_primary_count: 0,
              today_macro_count: 0,
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/digest")) {
          return new Response(
            JSON.stringify({
              counts: {
                pending_review_count: 0,
                pending_claims_count: 0,
                theses_challenged_count: 0,
                today_primary_count: 0,
                today_macro_count: 0,
              },
              today_highlights: [],
              pending_claims: [],
              challenged_items: [],
              early_signals: [],
              pending_facts: [],
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/items")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/signals")) {
          return new Response(
            JSON.stringify([
              {
                id: "sig_1",
                workspace_id: "ws_default",
                watchlist_id: "wl_ai",
                title: "NVIDIA / capex_signal",
                summary: "数据中心需求持续增强",
                signal_type: "capex_signal",
                first_seen_at: "2026-07-15T00:00:00Z",
                last_seen_at: "2026-07-15T01:00:00Z",
                source_count: 2,
                fact_ids: ["fact_1", "fact_2"],
                item_ids: ["inv_1", "inv_2"],
                confidence: 0.85,
                status: "tracking",
              },
            ]),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByText("早期信号")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA / capex_signal")).toBeInTheDocument();
    expect(screen.getByText("数据中心需求持续增强")).toBeInTheDocument();
    expect(screen.getByText("来源 2")).toBeInTheDocument();
    expect(screen.getByText("置信度 85%")).toBeInTheDocument();
    expect(screen.getByText("最近出现 07-15 09:00")).toBeInTheDocument();
  });

  it("shows challenged thesis items from the digest API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/dashboard")) {
          return new Response(
            JSON.stringify({
              pending_review_count: 0,
              pending_claims_count: 0,
              theses_challenged_count: 1,
              today_primary_count: 0,
              today_macro_count: 0,
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/digest")) {
          return new Response(
            JSON.stringify({
              counts: {
                pending_review_count: 0,
                pending_claims_count: 0,
                theses_challenged_count: 1,
                today_primary_count: 0,
                today_macro_count: 0,
              },
              today_highlights: [],
              pending_claims: [],
              challenged_items: [
                {
                  id: "item_challenge",
                  workspace_id: "ws_default",
                  dedupe_key: "item_challenge",
                  title: "Tariff policy may raise input costs",
                  title_zh: "关税政策可能抬升投入成本",
                  info_layer: "opinion",
                  source_credibility: "official",
                  importance: "high",
                  impact_direction: "negative",
                  impact_horizon: "short",
                  thesis_impact: "weakens",
                  action_status: "tracking",
                  published_at: "2026-07-16T08:00:00Z",
                },
              ],
              early_signals: [],
              pending_facts: [],
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/items")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/signals")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByText("关税政策可能抬升投入成本")).toBeInTheDocument();
    expect(screen.getByText("影响：weakens")).toBeInTheDocument();
    expect(screen.getByText("发布时间 07-16 16:00")).toBeInTheDocument();
  });
});

function metricCard(title: string) {
  const titleNode = screen.getByText(title);
  const card = titleNode.closest(".ant-card");
  expect(card).not.toBeNull();
  return card as HTMLElement;
}
