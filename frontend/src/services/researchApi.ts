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

export type ResearchImportResult = {
  task_id: string;
  document_id: string;
  task_job_ids: string[];
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
  /** Import a completed task's report into the knowledge base. */
  importReport(taskId: string) {
    return apiRequest<ResearchImportResult>(`/research/tasks/${taskId}/import`, {
      method: "POST",
    });
  },
  /** Reset a failed/finished task and re-run the workflow. */
  retry(taskId: string) {
    return apiRequest<ResearchTask>(`/research/tasks/${taskId}/retry`, {
      method: "POST",
    });
  },
};

