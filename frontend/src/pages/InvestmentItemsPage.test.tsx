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

  it("imports pasted X content as an opinion item", async () => {
    let createdBody: Record<string, unknown> | null = null;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/investment/items") && init?.method === "POST") {
        createdBody = JSON.parse(String(init.body));
        return new Response(
          JSON.stringify({
            id: "inv_x_manual",
            workspace_id: "ws_default",
            dedupe_key: "dk_x_manual",
            title: createdBody?.title,
            source_url: createdBody?.source_url,
            source_name: "X",
            info_layer: "opinion",
            source_credibility: "unverified",
            summary: createdBody?.summary,
            importance: "medium",
            impact_direction: "neutral",
            impact_horizon: "unknown",
            thesis_impact: "unknown",
            action_status: "pending_review",
          }),
          { status: 201 },
        );
      }
      if (u.includes("/investment/items")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "导入 X 内容" }));
    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "AI capex thread" },
    });
    fireEvent.change(screen.getByLabelText("X 链接"), {
      target: { value: "https://x.com/investor/status/123" },
    });
    fireEvent.change(screen.getByLabelText("正文/备注"), {
      target: { value: "Hyperscaler capex remains strong." },
    });
    const dialog = screen.getByRole("dialog", { name: "导入 X 内容" });
    fireEvent.click(within(dialog).getByRole("button", { name: /导\s*入/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/investment/items"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(createdBody).toMatchObject({
      title: "AI capex thread",
      source_url: "https://x.com/investor/status/123",
      source_name: "X",
      info_layer: "opinion",
      source_credibility: "unverified",
      summary: "Hyperscaler capex remains strong.",
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

  it("marks English items without Chinese fields as pending translation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_pending_translation",
                workspace_id: "ws_default",
                dedupe_key: "dk_pending_translation",
                title: "Federal Reserve issues FOMC statement",
                source_url: "https://www.federalreserve.gov/newsevents/pressreleases/x.htm",
                source_name: "Fed Monetary",
                info_layer: "macro_calendar",
                source_credibility: "official",
                published_at: "2026-06-17T18:00:00Z",
                summary: "The Committee described rates and inflation risks.",
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

    expect(await screen.findByText("待翻译")).toBeInTheDocument();
  });

  it("renders source urls as clickable external links", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_link",
                workspace_id: "ws_default",
                dedupe_key: "dk_link",
                title: "Fed policymakers' inflation concerns grew - Reuters",
                source_url: "https://www.reuters.com/markets/us/fed-minutes-2026-07-13/",
                source_name: "Google News - Fed",
                info_layer: "macro_calendar",
                source_credibility: "unverified",
                summary: "Federal Reserve officials were worried about inflation risks.",
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

    const sourceLink = await screen.findByRole("link", {
      name: "https://www.reuters.com/markets/us/fed-minutes-2026-07-13/",
    });
    expect(sourceLink).toHaveAttribute(
      "href",
      "https://www.reuters.com/markets/us/fed-minutes-2026-07-13/",
    );
    expect(sourceLink).toHaveAttribute("target", "_blank");
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

  it("loads and renders extracted facts in the detail drawer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items/inv_fact/facts")) {
          return new Response(
            JSON.stringify([
              {
                id: "fact_1",
                workspace_id: "ws_default",
                source_item_id: "inv_fact",
                watchlist_id: "wl_nvda",
                fact_text: "NVIDIA announced a new AI platform.",
                fact_text_zh: "英伟达宣布了新的 AI 平台。",
                fact_type: "company_update",
                entities: ["NVIDIA"],
                evidence_url: "https://x.com/nvidia/status/1",
                evidence_excerpt: "NVIDIA announced a new AI platform.",
                confidence: 0.82,
                verification_status: "pending",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/items")) {
          return new Response(
            JSON.stringify([
              {
                id: "inv_fact",
                workspace_id: "ws_default",
                dedupe_key: "dk_fact",
                title: "@nvidia: new platform",
                source_url: "https://x.com/nvidia/status/1",
                source_name: "@nvidia",
                info_layer: "opinion",
                source_credibility: "personal_opinion",
                summary: "NVIDIA announced a new AI platform.",
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
    expect(await within(drawer).findByText("英伟达宣布了新的 AI 平台。")).toBeInTheDocument();
    expect(within(drawer).getByText("置信度 82%")).toBeInTheDocument();
    expect(
      within(drawer).getByText("证据：NVIDIA announced a new AI platform."),
    ).toBeInTheDocument();
  });
});
