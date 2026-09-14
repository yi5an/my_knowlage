import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentThesesPage } from "./InvestmentThesesPage";

describe("InvestmentThesesPage outcome recording", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("does not silently select an unrelated opportunity", async () => {
    let outcomeCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/investment/theses")) {
          return new Response(
            JSON.stringify([
              {
                id: "thesis_1",
                workspace_id: "ws_default",
                title: "AI demand",
                body: "Demand remains strong",
                status: "open",
                confidence: "medium",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/watchlist")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/claims")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/opportunities")) {
          return new Response(
            JSON.stringify([
              {
                id: "opp_unrelated",
                workspace_id: "ws_default",
                title: "Unrelated opportunity",
                asset_symbols: ["TSLA"],
                opportunity_type: "catalyst",
                change_summary: "Change",
                expected_case: "Case",
                market_case: "Market",
                impact_path: "Path",
                catalyst: "Catalyst",
                next_action: "Verify",
                risk_flags: ["risk"],
                invalidation_conditions: ["Invalid"],
                evidence_refs: ["other_claim"],
                confidence: 0.5,
                status: "new",
                priority: "research",
                market_reaction_state: "unknown",
                score_breakdown: {},
                outcome: {},
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/recommendation-outcomes") && init?.method === "POST") {
          outcomeCalls += 1;
          return new Response(JSON.stringify({ id: "out_1" }), { status: 201 });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter>
        <InvestmentThesesPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "记录结果" }));
    expect(screen.getByText("选择要复盘的机会")).toBeInTheDocument();
    expect(outcomeCalls).toBe(0);
    expect(screen.getByText("记录假设结果")).toBeInTheDocument();
  });

  it("writes an outcome to the workspace from the page query", async () => {
    let outcomeBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/investment/theses")) {
          return new Response(
            JSON.stringify([
              {
                id: "thesis_alt",
                workspace_id: "ws_alt",
                title: "Alt workspace thesis",
                body: "Demand remains strong",
                status: "open",
                confidence: "medium",
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/watchlist")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/claims")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/opportunities")) {
          return new Response(
            JSON.stringify([
              {
                id: "opp_alt",
                workspace_id: "ws_alt",
                title: "Alt opportunity",
                asset_symbols: ["NVDA"],
                opportunity_type: "catalyst",
                change_summary: "Change",
                expected_case: "Case",
                market_case: "Market",
                impact_path: "Path",
                catalyst: "Catalyst",
                next_action: "Verify",
                risk_flags: ["risk"],
                invalidation_conditions: ["Invalid"],
                evidence_refs: ["claim_alt"],
                confidence: 0.5,
                status: "new",
                priority: "research",
                market_reaction_state: "unknown",
                score_breakdown: {},
                outcome: {},
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/recommendation-outcomes") && init?.method === "POST") {
          outcomeBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify({ id: "out_alt" }), { status: 201 });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter initialEntries={["/investment/theses?workspace_id=ws_alt"]}>
        <InvestmentThesesPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "记录结果" }));
    fireEvent.mouseDown(await screen.findByRole("combobox", { name: "关联机会" }));
    fireEvent.click(await screen.findByText("Alt opportunity"));
    fireEvent.click(screen.getByRole("button", { name: "保存结果" }));

    await waitFor(() => {
      expect(outcomeBody).toEqual(expect.objectContaining({
        workspace_id: "ws_alt",
        opportunity_id: "opp_alt",
      }));
    });
  });
});
