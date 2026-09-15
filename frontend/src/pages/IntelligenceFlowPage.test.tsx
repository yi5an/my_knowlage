import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { investmentFetchFixture } from "../test/fixtures/investmentFixtures";
import { IntelligenceFlowPage } from "./IntelligenceFlowPage";

function renderPage() {
  render(
    <MemoryRouter>
      <IntelligenceFlowPage />
    </MemoryRouter>,
  );
}

describe("IntelligenceFlowPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows at most five high-priority opportunity candidates", async () => {
    vi.stubGlobal("fetch", vi.fn(investmentFetchFixture({ opportunityCount: 8 })));
    renderPage();

    expect((await screen.findAllByTestId("opportunity-card")).length).toBe(5);
    expect(screen.getByText("查看全部机会候选")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /买入|卖出/ })).not.toBeInTheDocument();
  });

  it("separates information, signals, and opportunities", async () => {
    vi.stubGlobal("fetch", vi.fn(investmentFetchFixture()));
    renderPage();

    expect(await screen.findByText("最新情报")).toBeInTheDocument();
    expect(screen.getByText("正在发生")).toBeInTheDocument();
    expect(screen.getByText("高优先研究")).toBeInTheDocument();
  });

  it("renders loading, partial error, and retry states", async () => {
    let attempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        attempts += 1;
        if (url.includes("/investment/opportunities") && attempts < 5) {
          return new Response(JSON.stringify({ detail: "temporary error" }), { status: 503 });
        }
        return investmentFetchFixture()(url);
      }),
    );
    renderPage();

    expect(screen.getByText("正在加载情报流")).toBeInTheDocument();
    expect(await screen.findByText(/部分数据加载失败/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("最新情报")).toBeInTheDocument());
  });

  it("shows source freshness instead of claiming automatic 24-hour updates", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const value = String(url);
        if (value.includes("/investment/health")) {
          return new Response(JSON.stringify({
            workspace_id: "ws_default",
            generated_at: "2026-09-15T00:00:00Z",
            freshness_state: "stale",
            newest_item_at: "2026-09-12T00:00:00Z",
            newest_item_age_hours: 72,
            delayed_after_hours: 24,
            stale_after_hours: 48,
            sources: [{
              source_id: "src_fed",
              workspace_id: "ws_default",
              name: "美联储 RSS",
              source_type: "federal_reserve_rss",
              enabled: true,
              health_state: "stale",
              last_success_at: "2026-09-12T00:00:00Z",
              newest_item_at: "2026-09-12T00:00:00Z",
              newest_item_age_hours: 72,
              freshness_age_hours: 72,
              consecutive_failures: 0,
            }],
          }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        return investmentFetchFixture({ opportunityCount: 0, itemCount: 0, signalCount: 0 })(url);
      }),
    );
    renderPage();
    expect((await screen.findAllByText("数据已过期")).length).toBeGreaterThan(0);
    expect(screen.getByText(/美联储 RSS/)).toBeInTheDocument();
    expect(screen.getByText(/最近成功/)).toBeInTheDocument();
    expect(screen.queryByText("数据范围：过去 24 小时 · 自动更新")).not.toBeInTheDocument();
  });

  it("explains why there is no verifiable opportunity and offers refresh", async () => {
    vi.stubGlobal("fetch", vi.fn(investmentFetchFixture({ opportunityCount: 0 })));
    renderPage();
    expect(await screen.findByText("暂无可验证机会")).toBeInTheDocument();
    expect(screen.getByText(/当前没有可验证机会/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新机会" })).toBeInTheDocument();
  });
});
