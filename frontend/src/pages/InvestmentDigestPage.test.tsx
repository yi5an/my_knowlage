import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentDigestPage } from "./InvestmentDigestPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentDigestPage />
    </MemoryRouter>,
  );
}

describe("InvestmentDigestPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows early signals and pending facts from the digest API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/investment/digest")) {
          if (String(url).includes("/investment/digest/snapshots")) {
            return new Response(JSON.stringify([]), { status: 200 });
          }
          return new Response(
            JSON.stringify({
              counts: {
                pending_review_count: 1,
                pending_claims_count: 1,
                theses_challenged_count: 0,
                today_primary_count: 0,
                today_macro_count: 0,
              },
              today_highlights: [],
              pending_claims: [],
              challenged_items: [],
              early_signals: [
                {
                  id: "sig_digest",
                  workspace_id: "ws_default",
                  title: "NVIDIA / company_update",
                  summary: "英伟达宣布了一个平台。",
                  signal_type: "company_update",
                  first_seen_at: "2026-07-15T00:00:00Z",
                  last_seen_at: "2026-07-15T01:00:00Z",
                  source_count: 1,
                  fact_ids: ["fact_digest"],
                  item_ids: ["inv_digest"],
                  confidence: 0.8,
                  status: "tracking",
                },
              ],
              pending_facts: [
                {
                  id: "fact_digest",
                  workspace_id: "ws_default",
                  source_item_id: "inv_digest",
                  fact_text: "NVIDIA announced a platform.",
                  fact_text_zh: "英伟达宣布了一个平台。",
                  fact_type: "company_update",
                  entities: ["NVIDIA"],
                  evidence_url: "https://x.com/nvidia/status/1",
                  evidence_excerpt: "NVIDIA platform",
                  confidence: 0.8,
                  verification_status: "pending",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (String(url).includes("/investment/watchlist")) {
          return new Response(
            JSON.stringify([
              {
                id: "wl_ai",
                workspace_id: "ws_default",
                name: "AI Infra",
                watch_type: "theme",
                keywords: [],
                importance: "high",
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

    expect(await screen.findByText("NVIDIA / company_update")).toBeInTheDocument();
    expect(screen.getAllByText("英伟达宣布了一个平台。").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("证据：NVIDIA platform")).toBeInTheDocument();
    expect(screen.getAllByText("置信度 80%").length).toBeGreaterThanOrEqual(1);
  });

  it("requests digest scoped to selected watchlist", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/investment/digest/snapshots")) {
        return new Response(JSON.stringify([]), { status: 200 });
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
      if (u.includes("/investment/watchlist")) {
        return new Response(
          JSON.stringify([
            {
              id: "wl_ai",
              workspace_id: "ws_default",
              name: "AI Infra",
              watch_type: "theme",
              keywords: [],
              importance: "high",
              enabled: true,
            },
          ]),
          { status: 200 },
        );
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByText("AI Infra"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("watchlist_id=wl_ai"),
        expect.anything(),
      );
    });
  });

  it("saves a digest snapshot and reloads snapshot history", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/investment/digest/snapshots") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            id: "dig_1",
            workspace_id: "ws_default",
            digest_date: "2026-07-15T00:00:00Z",
            title: "每日简报",
            digest: {
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
            },
          }),
          { status: 201 },
        );
      }
      if (u.includes("/investment/digest/snapshots")) {
        return new Response(
          JSON.stringify([
            {
              id: "dig_1",
              workspace_id: "ws_default",
              digest_date: "2026-07-15T00:00:00Z",
              title: "每日简报",
              digest: {
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
              },
            },
          ]),
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
      if (u.includes("/investment/watchlist")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "保存快照" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/investment/digest/snapshots"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(screen.getAllByText("每日简报").length).toBeGreaterThanOrEqual(2);
    });
  });

  it("shows opportunity, person impact, and outcome sections in the digest", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/digest/snapshots")) {
          return new Response(JSON.stringify([]), { status: 200 });
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
              opportunities: [
                {
                  id: "opp_digest_ui",
                  workspace_id: "ws_default",
                  title: "AI capex inflection",
                  asset_symbols: ["NVDA"],
                  opportunity_type: "earnings_inflection",
                  change_summary: "Capex moved higher",
                  expected_case: "Demand remains above consensus",
                  market_case: "Price has not fully reacted",
                  impact_path: "Orders to revenue",
                  catalyst: "Next earnings",
                  next_action: "Verify guidance",
                  risk_flags: ["valuation"],
                  invalidation_conditions: ["Guidance cut"],
                  evidence_refs: ["item_digest"],
                  confidence: 0.82,
                  status: "new",
                  priority: "high_priority_research",
                  market_reaction_state: "partially_reacted",
                  score_breakdown: {},
                  outcome: {},
                },
              ],
              person_impact_events: [
                {
                  id: "impact_digest_ui",
                  workspace_id: "ws_default",
                  person_source_id: "person_digest",
                  source_item_id: "item_digest",
                  symbol: "NVDA",
                  benchmark_symbol: "SPY",
                  event_at: "2026-09-14T00:00:00Z",
                  event_cluster_id: "cluster_digest",
                  window_overlap: false,
                  event_status: "computed",
                  data_quality: "complete",
                  source_url: "https://x.com/analyst/status/1",
                  windows: {
                    "1d": { "excess_return": 0.02 },
                    "3d": { "excess_return": 0.04 },
                    "5d": { "excess_return": 0.06 },
                  },
                  concurrent_events: [],
                  confidence: 0.7,
                  reason: "事件研究已完成",
                },
              ],
              outcomes: [
                {
                  id: "outcome_digest_ui",
                  workspace_id: "ws_default",
                  opportunity_id: "opp_digest_ui",
                  adopted: true,
                  outcome_status: "invalidated",
                  outcome_note: "Guidance was cut",
                  observed_at: "2026-09-20T00:00:00Z",
                  recommendation_date: "2026-09-14T00:00:00Z",
                  failure_reason: "Guidance was cut",
                  metrics_reason: "数据缺失：尚未记录 3D/5D 行情结果。",
                  catalyst_result: "invalidated",
                  reason: "Guidance was cut",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (u.includes("/investment/watchlist")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByText("AI capex inflection")).toBeInTheDocument();
    expect(screen.getByText("人物影响事件")).toBeInTheDocument();
    const evidenceLink = screen.getByRole("link", { name: "查看原文证据" });
    expect(evidenceLink).toHaveAttribute("href", "https://x.com/analyst/status/1");
    expect(evidenceLink).toHaveAttribute("target", "_blank");
    expect(screen.getByText("结果复盘")).toBeInTheDocument();
    expect(screen.getByText(/Guidance was cut/)).toBeInTheDocument();
    expect(screen.getByText(/推荐日期/)).toBeInTheDocument();
    expect(screen.getByText(/数据缺失/)).toBeInTheDocument();
  });
});
