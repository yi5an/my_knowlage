import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "./client";
import { provenanceApi } from "./provenanceApi";

vi.mock("./client", () => ({ apiRequest: vi.fn() }));

const requestMock = vi.mocked(apiRequest);

describe("provenanceApi", () => {
  beforeEach(() => {
    requestMock.mockReset();
  });

  it("serializes defined overview filters and encodes values", async () => {
    await provenanceApi.overview(
      {
        layer: "event",
        display_status: "pending review",
        min_confidence: 0.55,
        conclusion_type: undefined,
        cursor: "page/2",
      },
      "workspace/a",
    );

    expect(requestMock).toHaveBeenCalledWith(
      "/provenance/overview?workspace_id=workspace%2Fa&layer=event&display_status=pending+review&min_confidence=0.55&cursor=page%2F2",
    );
  });

  it("requests both trace directions without reversing stored edges", async () => {
    await provenanceApi.traceNode("event/1", "up", "ws_default");
    await provenanceApi.traceNode("conclusion/1", "down", "ws_default", 120);

    expect(requestMock).toHaveBeenNthCalledWith(
      1,
      "/provenance/nodes/event%2F1/trace?workspace_id=ws_default&direction=up",
    );
    expect(requestMock).toHaveBeenNthCalledWith(
      2,
      "/provenance/nodes/conclusion%2F1/trace?workspace_id=ws_default&direction=down&max_nodes=120",
    );
  });

  it("loads edge detail and submits versioned review", async () => {
    await provenanceApi.edge("edge/1", "ws");
    await provenanceApi.reviewEdge(
      "edge/1",
      { action: "confirm", version_no: 3, reviewer_id: "me", note: "checked" },
      "ws",
    );

    expect(requestMock).toHaveBeenNthCalledWith(
      1,
      "/provenance/edges/edge%2F1?workspace_id=ws",
    );
    expect(requestMock).toHaveBeenNthCalledWith(
      2,
      "/provenance/edges/edge%2F1/review?workspace_id=ws",
      {
        method: "POST",
        body: { action: "confirm", version_no: 3, reviewer_id: "me", note: "checked" },
      },
    );
  });

  it("creates conclusions, rebuilds, and polls the durable job", async () => {
    const conclusion = {
      conclusion_type: "research" as const,
      title: "Supply is constrained",
      body: "Two sources support it.",
      confidence: 0.72,
    };
    await provenanceApi.createConclusion(conclusion, "workspace/a");
    await provenanceApi.rebuild("workspace/a", true);
    await provenanceApi.job("job/1", "workspace/a");

    expect(requestMock).toHaveBeenNthCalledWith(
      1,
      "/provenance/conclusions?workspace_id=workspace%2Fa",
      { method: "POST", body: conclusion },
    );
    expect(requestMock).toHaveBeenNthCalledWith(2, "/provenance/rebuild", {
      method: "POST",
      body: { workspace_id: "workspace/a", force: true },
    });
    expect(requestMock).toHaveBeenNthCalledWith(
      3,
      "/provenance/jobs/job%2F1?workspace_id=workspace%2Fa",
    );
  });
});
