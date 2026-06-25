import { apiRequest } from "./client";

export type ResearchTask = {
  id: string;
  workspace_id: string;
  title: string;
  question: string;
  status: string;
  report_doc_id: string | null;
  metadata: Record<string, unknown>;
};

export const researchApi = {
  list(workspaceId = "ws_default") {
    return apiRequest<ResearchTask[]>(`/research/tasks?workspace_id=${workspaceId}`);
  },
  create(question: string, workspaceId = "ws_default", title?: string) {
    return apiRequest<ResearchTask>("/research/tasks", {
      method: "POST",
      body: { workspace_id: workspaceId, question, title: title ?? question },
    });
  },
};

