import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentWatchlistPage } from "./InvestmentWatchlistPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentWatchlistPage />
    </MemoryRouter>,
  );
}

describe("InvestmentWatchlistPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows watchlist detail tabs with sources, latest items, signals, facts, and theses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/watchlist/wl_potus/sources")) {
          return new Response(
            JSON.stringify([
              {
                id: "src_potus",
                workspace_id: "ws_default",
                source_type: "x_web",
                name: "POTUS 官方",
                config: { mode: "account", username: "POTUS" },
                default_info_layer: "opinion",
                default_watchlist_ids: ["wl_potus"],
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
                id: "item_policy",
                workspace_id: "ws_default",
                source_id: "src_potus",
                dedupe_key: "item_policy",
                title: "Trump announced a tariff policy",
                title_zh: "特朗普宣布关税政策",
                info_layer: "opinion",
                source_credibility: "official",
                importance: "high",
                impact_direction: "uncertain",
                impact_horizon: "short",
                thesis_impact: "unknown",
                action_status: "pending_review",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/signals")) {
          return new Response(
            JSON.stringify([
              {
                id: "sig_policy",
                workspace_id: "ws_default",
                watchlist_id: "wl_potus",
                title: "关税政策信号",
                summary: "多个来源开始关注关税政策变化。",
                signal_type: "policy_update",
                first_seen_at: "2026-07-15T00:00:00Z",
                last_seen_at: "2026-07-15T01:00:00Z",
                source_count: 2,
                fact_ids: ["fact_policy"],
                item_ids: ["item_policy"],
                confidence: 0.82,
                status: "tracking",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/facts")) {
          return new Response(
            JSON.stringify([
              {
                id: "fact_policy",
                workspace_id: "ws_default",
                source_item_id: "item_policy",
                watchlist_id: "wl_potus",
                fact_text: "The president announced a tariff policy.",
                fact_text_zh: "总统宣布关税政策。",
                fact_type: "policy_update",
                entities: ["POTUS"],
                evidence_url: "https://x.com/POTUS/status/1",
                evidence_excerpt: "tariff policy",
                confidence: 0.85,
                verification_status: "pending",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/theses")) {
          return new Response(
            JSON.stringify([
              {
                id: "thesis_inflation",
                workspace_id: "ws_default",
                watchlist_id: "wl_potus",
                title: "关税抬升通胀",
                status: "active",
                confidence: "medium",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/watchlist")) {
          return new Response(
            JSON.stringify([
              {
                id: "wl_potus",
                workspace_id: "ws_default",
                name: "POTUS",
                watch_type: "official_account",
                ticker: null,
                exchange: null,
                keywords: ["Trump"],
                importance: "high",
                notes: null,
                enabled: true,
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/sources")) {
          return new Response(
            JSON.stringify([
              {
                id: "src_potus",
                workspace_id: "ws_default",
                source_type: "x_web",
                name: "POTUS 官方",
                config: { mode: "account", username: "POTUS" },
                default_info_layer: "opinion",
                default_watchlist_ids: ["wl_potus"],
                poll_interval_seconds: 900,
                enabled: true,
              },
            ]),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByText("POTUS")).toBeInTheDocument();
    expect(screen.getByText("信息源")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("POTUS 官方").length).toBeGreaterThanOrEqual(2);
    });

    fireEvent.click(screen.getByText("最新信息"));
    expect(await screen.findByText("特朗普宣布关税政策")).toBeInTheDocument();

    fireEvent.click(screen.getByText("早期信号"));
    expect(await screen.findByText("关税政策信号")).toBeInTheDocument();
    expect(screen.getByText("证据：tariff policy")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开证据" })).toHaveAttribute(
      "href",
      "https://x.com/POTUS/status/1",
    );

    fireEvent.click(screen.getByText("待验证事实"));
    expect(await screen.findByText("总统宣布关税政策。")).toBeInTheDocument();

    fireEvent.click(screen.getByText("相关假设"));
    expect(await screen.findByText("关税抬升通胀")).toBeInTheDocument();
  });

  it("offers source management actions from the selected watchlist", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/watchlist/wl_nvda/sources")) return Response.json([]);
        if (u.includes("/investment/items") || u.includes("/investment/signals") || u.includes("/investment/facts") || u.includes("/investment/theses")) return Response.json([]);
        if (u.includes("/investment/watchlist")) {
          return Response.json([{ id: "wl_nvda", workspace_id: "ws_default", name: "NVIDIA", watch_type: "stock", keywords: [], importance: "high", enabled: true }]);
        }
        if (u.includes("/investment/sources")) return Response.json([]);
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByRole("button", { name: "绑定已有信息源" })).toBeInTheDocument();
  });

  it("creates an object, binds selected sources, and starts their first fetch", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/investment/watchlist") && init?.method === "POST") {
        return Response.json({ id: "wl_nvda", workspace_id: "ws_default", name: "NVIDIA", watch_type: "stock", keywords: [], importance: "high", enabled: true });
      }
      if (u.includes("/watchlist/wl_nvda/sources/src_rss") && init?.method === "POST") return Response.json({ id: "src_rss" });
      if (u.includes("/sources/src_rss/poll") && init?.method === "POST") return Response.json({ job_id: "job_rss", status: "pending" });
      if (u.includes("/investment/watchlist/wl_nvda/sources")) return Response.json([]);
      if (u.includes("/investment/items") || u.includes("/investment/signals") || u.includes("/investment/facts") || u.includes("/investment/theses")) return Response.json([]);
      if (u.includes("/investment/watchlist")) return Response.json([]);
      if (u.includes("/investment/sources")) return Response.json([{ id: "src_rss", workspace_id: "ws_default", source_type: "rss", name: "NVIDIA IR RSS", config: {}, default_info_layer: "news", default_watchlist_ids: [], poll_interval_seconds: 3600, enabled: true }]);
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "添加观察对象" }));
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "NVIDIA" } });
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    expect(await screen.findByText("配置首批信息源")).toBeInTheDocument();
    expect(screen.getByText("推荐信息源模板")).toBeInTheDocument();
  });
});
