import { apiRequest } from "./client";

export type DocumentSummary = {
  id: string;
  title: string;
  status: string;
};

export const documentApi = {
  list(workspaceId: string) {
    return apiRequest<DocumentSummary[]>(`/documents?workspace_id=${workspaceId}`);
  },
  get(documentId: string) {
    return apiRequest<DocumentSummary>(`/documents/${documentId}`);
  },
};

