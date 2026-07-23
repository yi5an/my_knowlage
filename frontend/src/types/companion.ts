export type CompanionSubjectType = "document" | "youtube_video" | "information_edge" | "workspace";
export type CompanionRelation = "primary" | "corroborates" | "conflicts";
export type CompanionInsightKind = "focus" | "question" | "risk" | "opportunity";

export type CompanionContext = {
  workspaceId: string;
  subjectType: CompanionSubjectType;
  subjectId: string;
  title: string;
};

export type CompanionCitation = {
  source_id: string;
  source_title: string;
  excerpt: string;
  relation: CompanionRelation;
  confidence: number;
};

export type CompanionMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: CompanionCitation[];
  confidence: number | null;
};

export type CompanionInsight = {
  id: string;
  kind: CompanionInsightKind;
  headline: string;
  content: string;
  citations: CompanionCitation[];
  confidence: number;
  status: string;
};

export type CompanionSession = {
  id: string;
  workspace_id: string;
  subject_type: CompanionSubjectType;
  subject_id: string;
  title: string;
  status: string;
};

export type CompanionSessionDetail = CompanionSession & {
  messages: CompanionMessage[];
  insights: CompanionInsight[];
};
