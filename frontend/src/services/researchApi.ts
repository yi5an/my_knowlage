import { apiRequest } from "./client";

export type ResearchTask = {
  id: string;
  title: string;
  status: string;
};

export const researchApi = {
  list(workspaceId: string) {
    return apiRequest<ResearchTask[]>(`/research/tasks?workspace_id=${workspaceId}`);
  },
  create(question: string) {
    return apiRequest<ResearchTask>("/research/tasks", { method: "POST", body: { question } });
  },
};

