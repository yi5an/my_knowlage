import { apiRequest } from "./client";

export type EntitySummary = {
  id: string;
  workspace_id: string;
  entity_type_id: string;
  name: string;
  normalized_name: string;
  aliases: string[];
  description: string | null;
  properties: { zh_name?: string; [key: string]: unknown };
  confidence: number;
  verified: boolean;
};

export const entityApi = {
  get(entityId: string) {
    return apiRequest<EntitySummary>(`/entities/${entityId}`);
  },
  list(workspaceId: string) {
    return apiRequest<EntitySummary[]>(`/entities?workspace_id=${workspaceId}`);
  },
};

