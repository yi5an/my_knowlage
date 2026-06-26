import { apiRequest } from "./client";

/** A citation backing a RAG answer. Mirrors backend Citation (rag.py). */
export type Citation = {
  document_id: string;
  chunk_id: string;
  title: string;
  quote: string;
  confidence: number;
};

export type RelatedEntity = {
  entity_id: string;
  name: string;
  entity_type: string;
  relation?: string;
};

/** Mirrors backend ChatQueryResponse (rag.py). */
export type ChatAnswer = {
  answer: string;
  citations: Citation[];
  related_entities: RelatedEntity[];
};

export const searchApi = {
  /** Ask a question; the backend retrieves chunks + entities and answers. */
  ask(question: string, workspaceId = "ws_default", limit = 5) {
    return apiRequest<ChatAnswer>("/chat/query", {
      method: "POST",
      body: { question, workspace_id: workspaceId, limit },
    });
  },
};
