import { apiRequest } from "./client";

export type GraphSnapshot = {
  nodes: Array<{ id: string; label: string }>;
  edges: Array<{ source: string; target: string; type: string }>;
};

export const graphApi = {
  getWorkspaceGraph(workspaceId: string) {
    return apiRequest<GraphSnapshot>(`/graph?workspace_id=${workspaceId}`);
  },
};

