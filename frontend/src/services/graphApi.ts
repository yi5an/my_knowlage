import { apiRequest } from "./client";

export interface GraphNode {
  id: string;
  label: string;
  node_type: string;
  properties?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  confidence?: number | null;
  evidence?: string | null;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export const graphApi = {
  search(query: string, workspaceId = "ws_default", limit = 50): Promise<GraphResponse> {
    return apiRequest<GraphResponse>("/graph/search", {
      method: "POST",
      body: { query, workspace_id: workspaceId, limit },
    });
  },

  neighbors(entityId: string, depth = 2, limit = 50): Promise<GraphResponse> {
    return apiRequest<GraphResponse>(
      `/graph/entities/${entityId}/neighbors?depth=${depth}&limit=${limit}`,
    );
  },

  sync(workspaceId = "ws_default"): Promise<{ workspace_id: string; node_count: number; edge_count: number }> {
    return apiRequest(`/graph/sync?workspace_id=${workspaceId}`, { method: "POST" });
  },
};
