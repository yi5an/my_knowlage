import { apiRequest } from "./client";

export type Annotation = {
  id: string;
  docId: string;
  selectedText: string;
  note: string;
};

export const annotationApi = {
  list(documentId: string) {
    return apiRequest<Annotation[]>(`/annotations?document_id=${documentId}`);
  },
  create(annotation: Omit<Annotation, "id">) {
    return apiRequest<Annotation>("/annotations", { method: "POST", body: annotation });
  },
};
