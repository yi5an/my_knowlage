import { apiRequest } from "./client";
import type { ReadingAnalysis, ReaderDocument } from "../types/readingCompanion";

export const readingCompanionApi = {
  getReader(documentId: string) {
    return apiRequest<ReaderDocument>(`/documents/${documentId}/reader`);
  },
  trigger(documentId: string) {
    return apiRequest<{ analysis_id: string; task_job_id: string; status: ReadingAnalysis["status"] }>(
      `/documents/${documentId}/reading-analyses`,
      { method: "POST" },
    );
  },
  getAnalysis(analysisId: string) {
    return apiRequest<ReadingAnalysis>(`/reading-analyses/${analysisId}`);
  },
  updateInsight(insightId: string, status: "confirmed" | "dismissed") {
    return apiRequest(`/reading-insights/${insightId}`, { method: "PATCH", body: { status } });
  },
};
