import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InformationEdgePage } from "./InformationEdgePage";

describe("InformationEdgePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows scored early signals and source traces", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/investment/information-edge")) {
          return new Response(
            JSON.stringify({
              generated_at: "2026-07-15T00:00:00Z",
              top_signals: [
                {
                  id: "sig_ai",
                  workspace_id: "ws_default",
                  title: "NVDA / capex_signal",
                  summary: "多源重复出现 AI capex 扩张信号。",
                  signal_type: "capex_signal",
                  first_seen_at: "2026-07-15T00:00:00Z",
                  last_seen_at: "2026-07-15T02:00:00Z",
                  source_count: 2,
                  fact_ids: ["fact_1"],
                  item_ids: ["inv_1"],
                  confidence: 0.8,
                  status: "tracking",
                  signal_stage: "repeating",
                  source_layers: ["primary_source", "human_source"],
                  first_source_layer: "human_source",
                  validation_state: "pending",
                  lead_time_hours: 18,
                  information_edge_score: 0.76,
                  actionability: "immediate_attention",
                  score_breakdown: { lead_time_score: 0.8 },
                },
              ],
              source_traces: [
                {
                  id: "trace_ai",
                  workspace_id: "ws_default",
                  target_item_id: "inv_youtube",
                  source_item_id: "inv_1",
                  trace_type: "likely_source",
                  match_reason: "earlier source",
                  matched_fact: "AI capex",
                  lead_time_hours: 18,
                  confidence: 0.82,
                },
              ],
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
        <InformationEdgePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("信息差系统")).toBeInTheDocument();
    });
    expect(screen.getByText("NVDA / capex_signal")).toBeInTheDocument();
    expect(screen.getByText("领先 18 小时")).toBeInTheDocument();
    expect(screen.getByText("likely_source")).toBeInTheDocument();
  });
});
