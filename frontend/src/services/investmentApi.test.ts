import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "./client";
import { investmentApi } from "./investmentApi";

vi.mock("./client", () => ({ apiRequest: vi.fn() }));

const requestMock = vi.mocked(apiRequest);

describe("investment opportunity discovery API", () => {
  beforeEach(() => {
    requestMock.mockReset();
  });

  it("lists and reviews opportunity candidates with workspace filters", async () => {
    await investmentApi.listOpportunityCandidates({
      workspaceId: "workspace/a",
      status: "researching",
      limit: 5,
    });
    await investmentApi.reviewOpportunityCandidate(
      "opp/1",
      { status: "validated", note: "Catalyst confirmed" },
      "workspace/a",
    );

    expect(requestMock).toHaveBeenNthCalledWith(
      1,
      "/investment/opportunities?workspace_id=workspace%2Fa&status=researching&limit=5",
    );
    expect(requestMock).toHaveBeenNthCalledWith(
      2,
      "/investment/opportunities/opp%2F1?workspace_id=workspace%2Fa",
      { method: "PATCH", body: { status: "validated", note: "Catalyst confirmed" } },
    );
  });

  it("supports account recommendations, person impact, context, and outcomes", async () => {
    await investmentApi.listAccountRecommendations({
      workspaceId: "ws/a",
      platform: "youtube",
      themeId: "theme/ai",
    });
    await investmentApi.followAccountRecommendation(
      "rec/1",
      { theme_ids: ["theme/ai"], poll_interval_seconds: 900 },
      "ws/a",
    );
    await investmentApi.listPersonImpactEvents("person/1", 25, "ws/a");
    await investmentApi.getPersonImpactProfile("person/1", "ws/a");
    await investmentApi.getUserInvestmentContext("ws/a");
    await investmentApi.updateUserInvestmentContext(
      { markets: ["us"], horizons: ["mid"] },
      "ws/a",
    );
    await investmentApi.createRecommendationOutcome({
      workspace_id: "ws/a",
      opportunity_id: "opp_1",
      adopted: true,
      outcome_status: "validated",
      observed_at: "2026-09-20T00:00:00Z",
    });

    expect(requestMock).toHaveBeenNthCalledWith(
      1,
      "/investment/account-recommendations?workspace_id=ws%2Fa&platform=youtube&theme_id=theme%2Fai",
    );
    expect(requestMock).toHaveBeenNthCalledWith(
      2,
      "/investment/account-recommendations/rec%2F1/follow?workspace_id=ws%2Fa",
      { method: "POST", body: { theme_ids: ["theme/ai"], poll_interval_seconds: 900 } },
    );
    expect(requestMock).toHaveBeenNthCalledWith(
      3,
      "/investment/person-sources/person%2F1/impact-events?workspace_id=ws%2Fa&limit=25",
    );
    expect(requestMock).toHaveBeenNthCalledWith(
      4,
      "/investment/person-sources/person%2F1/impact-profile?workspace_id=ws%2Fa",
    );
    expect(requestMock).toHaveBeenNthCalledWith(5, "/investment/context?workspace_id=ws%2Fa");
    expect(requestMock).toHaveBeenNthCalledWith(
      6,
      "/investment/context?workspace_id=ws%2Fa",
      { method: "PATCH", body: { markets: ["us"], horizons: ["mid"] } },
    );
    expect(requestMock).toHaveBeenNthCalledWith(7, "/investment/recommendation-outcomes", {
      method: "POST",
      body: {
        workspace_id: "ws/a",
        opportunity_id: "opp_1",
        adopted: true,
        outcome_status: "validated",
        observed_at: "2026-09-20T00:00:00Z",
      },
    });
  });
});
