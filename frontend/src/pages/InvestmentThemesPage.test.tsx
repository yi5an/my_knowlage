import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentThemesPage } from "./InvestmentThemesPage";

describe("InvestmentThemesPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows theme-first tracking domains", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/investment/themes")) {
          return new Response(
            JSON.stringify([
              {
                id: "theme_ai",
                workspace_id: "ws_default",
                name: "AI 算力",
                description: "GPU, HBM, data center power",
                theme_type: "sector",
                keywords: ["HBM", "数据中心电力"],
                entities: ["NVDA", "AMD"],
                tickers: ["NVDA", "AMD"],
                enabled: true,
                priority: "high",
              },
            ]),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter>
        <InvestmentThemesPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("主题中心")).toBeInTheDocument();
    expect(screen.getByText("AI 算力")).toBeInTheDocument();
    expect(screen.getByText("HBM")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  it("shows how a selected theme connects to sources, items and signals", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/themes/theme_ai/sources")) {
          return new Response(
            JSON.stringify([
              {
                id: "bind_ai_source",
                workspace_id: "ws_default",
                theme_id: "theme_ai",
                source_id: "src_nvidia",
                source_layer: "human_source",
                priority: 80,
                enabled: true,
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/themes")) {
          return new Response(
            JSON.stringify([
              {
                id: "theme_ai",
                workspace_id: "ws_default",
                name: "AI 算力",
                description: "GPU, HBM, data center power",
                theme_type: "sector",
                keywords: ["HBM"],
                entities: ["NVIDIA"],
                tickers: ["NVDA"],
                enabled: true,
                priority: "high",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/sources")) {
          return new Response(
            JSON.stringify([
              {
                id: "src_nvidia",
                workspace_id: "ws_default",
                source_type: "x_web",
                name: "NVIDIA X",
                config: { mode: "account", username: "nvidia" },
                default_info_layer: "opinion",
                default_watchlist_ids: [],
                poll_interval_seconds: 900,
                enabled: true,
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_ai",
                workspace_id: "ws_default",
                theme_id: "theme_ai",
                source_id: "src_nvidia",
                dedupe_key: "ai",
                title: "NVIDIA AI factories need more power",
                title_zh: "英伟达 AI 工厂需要更多电力",
                source_name: "@nvidia",
                info_layer: "opinion",
                source_credibility: "personal_opinion",
                importance: "medium",
                impact_direction: "neutral",
                impact_horizon: "unknown",
                thesis_impact: "unknown",
                action_status: "pending_review",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/information-edge")) {
          return new Response(
            JSON.stringify({
              generated_at: "2026-07-15T00:00:00Z",
              top_signals: [
                {
                  id: "sig_ai",
                  workspace_id: "ws_default",
                  theme_id: "theme_ai",
                  title: "NVIDIA / capex_signal",
                  summary: "AI capex signal",
                  signal_type: "capex_signal",
                  first_seen_at: "2026-07-15T00:00:00Z",
                  last_seen_at: "2026-07-15T01:00:00Z",
                  source_count: 2,
                  fact_ids: [],
                  item_ids: ["inv_ai"],
                  confidence: 0.8,
                  status: "tracking",
                  information_edge_score: 0.7,
                },
              ],
              source_traces: [],
              unvalidated_signals: [],
              stale_or_noise: [],
            }),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter>
        <InvestmentThemesPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("AI 算力控制台")).toBeInTheDocument();
    expect(await screen.findByText("NVIDIA X")).toBeInTheDocument();
    expect(await screen.findByText("英伟达 AI 工厂需要更多电力")).toBeInTheDocument();
    expect(await screen.findByText("NVIDIA / capex_signal")).toBeInTheDocument();
  });

  it("keeps long theme item summaries constrained inside the card", async () => {
    const longSummary =
      "https://x.com/nvidia/status/12345678901234567890 " +
      "英伟达正在扩展 AI 实验室和企业 API 使用场景，这是一段很长的主题信息摘要，用来确保文本不会撑破最近主题信息卡片。";

    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/themes/theme_ai/sources")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/themes")) {
          return new Response(
            JSON.stringify([
              {
                id: "theme_ai",
                workspace_id: "ws_default",
                name: "AI 算力",
                theme_type: "sector",
                keywords: ["GPU"],
                entities: ["NVIDIA"],
                tickers: ["NVDA"],
                enabled: true,
                priority: "high",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/sources")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_long",
                workspace_id: "ws_default",
                theme_id: "theme_ai",
                dedupe_key: "long",
                title: "NVIDIA long summary item",
                title_zh: "英伟达长摘要信息",
                summary_zh: longSummary,
                source_name: "@nvidia",
                info_layer: "opinion",
                source_credibility: "personal_opinion",
                importance: "medium",
                impact_direction: "neutral",
                impact_horizon: "unknown",
                thesis_impact: "unknown",
                action_status: "pending_review",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/information-edge")) {
          return new Response(
            JSON.stringify({
              generated_at: "2026-07-15T00:00:00Z",
              top_signals: [],
              source_traces: [],
              unvalidated_signals: [],
              stale_or_noise: [],
            }),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter>
        <InvestmentThemesPage />
      </MemoryRouter>,
    );

    const summary = await screen.findByText(longSummary);
    expect(summary).toHaveClass("investment-theme-text");
  });
});
