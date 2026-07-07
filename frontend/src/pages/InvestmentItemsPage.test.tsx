import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvestmentItemsPage } from "./InvestmentItemsPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentItemsPage />
    </MemoryRouter>,
  );
}

describe("InvestmentItemsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
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

  it("renders the heading and real empty state", async () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "投资信息" })).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText("暂无投资信息（创建数据源并抓取后会出现真实条目）"),
      ).toBeInTheDocument();
    });
  });

  it("can trigger translation for untranslated items", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/investment/items/translate")) {
        return new Response(JSON.stringify({ translated: 2, skipped: 1 }), { status: 200 });
      }
      if (u.includes("/investment/items")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "翻译未翻译内容" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/investment/items/translate"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("renders the collected summary under the title", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_1",
                workspace_id: "ws_default",
                dedupe_key: "dk_1",
                title: "Federal Reserve issues FOMC statement",
                source_url: "https://www.federalreserve.gov/newsevents/pressreleases/x.htm",
                source_name: "Fed Monetary",
                info_layer: "macro_calendar",
                source_credibility: "official",
                published_at: "2026-06-17T18:00:00Z",
                summary:
                  "The Federal Open Market Committee approved a statement describing rates and inflation risks.",
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
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(
          "The Federal Open Market Committee approved a statement describing rates and inflation risks.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("filters by translated title and summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_zh_search",
                workspace_id: "ws_default",
                dedupe_key: "dk_zh_search",
                title: "Federal Reserve releases projections",
                title_zh: "美联储经济预测",
                source_url: "https://www.federalreserve.gov/x.htm",
                source_name: "Fed Monetary",
                info_layer: "macro_calendar",
                source_credibility: "official",
                summary: "Projection tables.",
                summary_zh: "附件包含联邦基金利率路径。",
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
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("美联储经济预测")).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText("搜索标题或来源"), {
      target: { value: "利率路径" },
    });

    expect(screen.getByText("美联储经济预测")).toBeInTheDocument();
  });

  it("opens a readable detail drawer with content and source link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_detail",
                workspace_id: "ws_default",
                dedupe_key: "dk_detail",
                title: "Federal Reserve issues FOMC statement",
                title_zh: "美联储发布FOMC声明",
                source_url: "https://www.federalreserve.gov/newsevents/pressreleases/x.htm",
                source_name: "Fed Monetary",
                info_layer: "macro_calendar",
                source_credibility: "official",
                published_at: "2026-06-17T18:00:00Z",
                summary:
                  "The Committee decided to maintain the target range for the federal funds rate and described inflation risks.",
                summary_zh:
                  "委员会决定维持联邦基金利率目标区间，并描述了通胀风险。",
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
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "查看详情" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("内容详情")).toBeInTheDocument();
    expect(
      within(drawer).getByText("委员会决定维持联邦基金利率目标区间，并描述了通胀风险。"),
    ).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "打开源站原文" })).toHaveAttribute(
      "href",
      "https://www.federalreserve.gov/newsevents/pressreleases/x.htm",
    );
  });

  it("shows attachments and attachment content in the detail drawer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_attachment",
                workspace_id: "ws_default",
                dedupe_key: "dk_attachment",
                title: "Fed economic projections",
                title_zh: "美联储经济预测",
                source_url: "https://www.federalreserve.gov/newsevents/pressreleases/x.htm",
                source_name: "Fed Monetary",
                info_layer: "macro_calendar",
                source_credibility: "official",
                published_at: "2026-06-17T18:00:00Z",
                summary: "The attached tables and charts summarize economic projections.",
                summary_zh: "附件表格和图表汇总了经济预测。",
                attachments: [
                  {
                    title: "Accessible Materials",
                    url: "https://www.federalreserve.gov/monetarypolicy/projections.htm",
                    content_type: "html",
                    text_excerpt: "Median federal funds rate 3.6 percent.",
                  },
                ],
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
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "查看详情" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("附件")).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Accessible Materials" })).toHaveAttribute(
      "href",
      "https://www.federalreserve.gov/monetarypolicy/projections.htm",
    );
    expect(
      within(drawer).getByText("Median federal funds rate 3.6 percent."),
    ).toBeInTheDocument();
  });
});
