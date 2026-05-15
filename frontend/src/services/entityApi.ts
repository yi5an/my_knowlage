import { apiRequest } from "./client";

export type EntitySummary = {
  id: string;
  name: string;
  type: string;
};

export const entityApi = {
  get(entityId: string) {
    return apiRequest<EntitySummary>(`/entities/${entityId}`);
  },
  list(workspaceId: string) {
    return apiRequest<EntitySummary[]>(`/entities?workspace_id=${workspaceId}`);
  },
};

