export type InsightKind = "understanding" | "impact" | "risk";
export type EvidenceState = "corroborated" | "conflicted" | "insufficient";
export type InsightStatus = "active" | "confirmed" | "dismissed";

export type ReadingCorroboration = {
  id: string;
  source_kind: string;
  source_id: string;
  document_id: string | null;
  chunk_id: string | null;
  stance: "supports" | "contradicts" | "contextualizes";
  excerpt: string;
  source_title: string;
  source_published_at: string | null;
  confidence: number;
  retrieval_score: number;
};

export type ReadingInsight = {
  id: string;
  kind: InsightKind;
  headline: string;
  explanation: string;
  why_it_matters: string;
  chunk_id: string;
  start_offset: number;
  end_offset: number;
  evidence_text: string;
  confidence: number;
  priority: number;
  evidence_state: EvidenceState;
  status: InsightStatus;
  user_note: string | null;
  theme_ids: string[];
  macro_event_ids: string[];
  entity_ids: string[];
  corroborations: ReadingCorroboration[];
};

export type ReadingAnalysis = {
  id: string;
  workspace_id: string;
  document_id: string;
  version_id: string;
  status: "pending" | "running" | "completed" | "failed";
  task_job_id: string | null;
  error_message: string | null;
  insights: ReadingInsight[];
};

export type ReaderDocument = {
  document_id: string;
  workspace_id: string;
  version_id: string;
  title: string;
  content_md: string;
  chunks: Array<{ id: string; heading: string | null; content: string }>;
  analysis: ReadingAnalysis | null;
};
