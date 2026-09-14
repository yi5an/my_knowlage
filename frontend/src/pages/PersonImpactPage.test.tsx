import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { personImpactFixture } from "../test/fixtures/investmentFixtures";
import { PersonImpactPage } from "./PersonImpactPage";

describe("PersonImpactPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows insufficient sample instead of an impact conclusion", async () => {
    const fixture = personImpactFixture();
    const profileResponse = await fixture("impact-profile");
    const profile = {
      ...(await profileResponse.json()),
      valid_sample_count: 3,
      sample_sufficient: false,
      uncertainty: "样本不足",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const body = url.includes("impact-profile")
          ? profile
          : [
              {
                id: "impact_event_fixture",
                workspace_id: "ws_default",
                person_source_id: profile.person_source_id,
                source_item_id: "item_fixture_0",
                symbol: "NVDA",
                benchmark_symbol: "SPY",
                event_at: "2026-09-13T08:00:00Z",
                event_cluster_id: "cluster_fixture",
                window_overlap: false,
                event_status: "insufficient_data",
                data_quality: "missing",
                windows: {},
                concurrent_events: [],
                exclusion_reason: "样本不足",
                confidence: 0,
              },
            ];
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    render(
      <MemoryRouter initialEntries={["/investment/person-sources/person_fixture/impact"]}>
        <Routes>
          <Route
            path="/investment/person-sources/:personId/impact"
            element={<PersonImpactPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect((await screen.findAllByText("样本不足")).length).toBeGreaterThan(0);
    expect(screen.queryByText("影响较强")).not.toBeInTheDocument();
  });
});
