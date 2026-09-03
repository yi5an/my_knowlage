import type {
  Conclusion,
  ConclusionCreate,
  ProvenanceGraphResponse,
  ProvenanceJob,
  ProvenanceOverviewFilters,
  ProvenanceRebuildResponse,
  TraceDirection,
  TraceEdgeDetail,
  TraceEdgeReviewRequest,
  TraceEdgeReviewResponse,
} from "../types/provenance";
import { apiRequest } from "./client";

const DEFAULT_WORKSPACE_ID = "ws_default";

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) search.set(key, String(value));
  });
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

export const provenanceApi = {
  overview(
    filters: ProvenanceOverviewFilters = {},
    workspaceId = DEFAULT_WORKSPACE_ID,
  ): Promise<ProvenanceGraphResponse> {
    return apiRequest(
      `/provenance/overview${query({ workspace_id: workspaceId, ...filters })}`,
    );
  },

  traceNode(
    nodeId: string,
    direction: TraceDirection,
    workspaceId = DEFAULT_WORKSPACE_ID,
    maxNodes?: number,
  ): Promise<ProvenanceGraphResponse> {
    return apiRequest(
      `/provenance/nodes/${encodeURIComponent(nodeId)}/trace${query({
        workspace_id: workspaceId,
        direction,
        max_nodes: maxNodes,
      })}`,
    );
  },

  edge(edgeId: string, workspaceId = DEFAULT_WORKSPACE_ID): Promise<TraceEdgeDetail> {
    return apiRequest(
      `/provenance/edges/${encodeURIComponent(edgeId)}${query({
        workspace_id: workspaceId,
      })}`,
    );
  },

  reviewEdge(
    edgeId: string,
    body: TraceEdgeReviewRequest,
    workspaceId = DEFAULT_WORKSPACE_ID,
  ): Promise<TraceEdgeReviewResponse> {
    return apiRequest(
      `/provenance/edges/${encodeURIComponent(edgeId)}/review${query({
        workspace_id: workspaceId,
      })}`,
      { method: "POST", body },
    );
  },

  createConclusion(
    body: ConclusionCreate,
    workspaceId = DEFAULT_WORKSPACE_ID,
  ): Promise<Conclusion> {
    return apiRequest(
      `/provenance/conclusions${query({ workspace_id: workspaceId })}`,
      { method: "POST", body },
    );
  },

  rebuild(
    workspaceId = DEFAULT_WORKSPACE_ID,
    force = false,
  ): Promise<ProvenanceRebuildResponse> {
    return apiRequest("/provenance/rebuild", {
      method: "POST",
      body: { workspace_id: workspaceId, force },
    });
  },

  job(jobId: string, workspaceId = DEFAULT_WORKSPACE_ID): Promise<ProvenanceJob> {
    return apiRequest(
      `/provenance/jobs/${encodeURIComponent(jobId)}${query({
        workspace_id: workspaceId,
      })}`,
    );
  },
};
