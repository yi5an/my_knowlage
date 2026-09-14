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
});
