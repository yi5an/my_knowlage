import { apiRequest } from "./client";

/** Mirrors backend DocumentSummary (schemas/documents.py). */
export type DocumentSummary = {
  id: string;
  workspace_id: string;
  title: string;
  source_type: string;
  status: string;
  parse_status: string;
  content_type: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type DocumentImportResponse = {
  document_id: string | null;
  task_job_id: string;
  status: string;
  duplicate?: boolean;
};

export const documentApi = {
  list(workspaceId = "ws_default") {
    return apiRequest<DocumentSummary[]>(`/documents?workspace_id=${workspaceId}`);
  },
  get(documentId: string) {
    return apiRequest<DocumentSummary>(`/documents/${documentId}`);
  },
  importUrl(url: string, workspaceId = "ws_default", title?: string) {
    return apiRequest<DocumentImportResponse>("/documents/import/url", {
      method: "POST",
      body: { workspace_id: workspaceId, url, title: title ?? url },
    });
  },
  importFile(file: File, workspaceId = "ws_default") {
    const form = new FormData();
    form.append("file", file);
    form.append("workspace_id", workspaceId);
    return apiRequest<DocumentImportResponse>("/documents/import/file", {
      method: "POST",
      body: form,
    });
  },
};
