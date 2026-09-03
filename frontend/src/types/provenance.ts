export type TraceLayer = "conclusion" | "event" | "evidence";
export type TraceDirection = "up" | "down";
export type TraceRelationType =
  | "supports"
  | "refutes"
  | "qualifies"
  | "explains"
  | "causes"
  | "derived_from"
  | "aggregates"
  | "related_unconfirmed";
export type ReviewStatus =
  | "ai_generated"
  | "pending_review"
  | "confirmed"
  | "rejected";
export type ValidationStatus =
  | "unverified"
  | "supported"
  | "refuted"
  | "conflicted"
  | "insufficient_evidence";
export type EvidenceValidationState = "valid" | "stale" | "invalid";
export type OriginType = "ai" | "user" | "imported" | "rule";
export type ReviewAction = "confirm" | "reject" | "mark_conflict" | "reset_pending";

export type EvidenceLocator =
  | {
      type: "text_span";
      chunk_id: string;
      start_offset: number;
      end_offset: number;
    }
  | {
      type: "pdf_region";
      page_no: number;
      bbox: [number, number, number, number];
      chunk_id?: string | null;
    }
  | {
      type: "media_segment";
      start_ms: number;
      end_ms: number;
      chunk_id?: string | null;
    }
  | {
      type: "image_region";
      frame_id: string;
      bbox: [number, number, number, number];
      ocr_block_ids: string[];
    }
  | {
      type: "web_fragment";
      fragment_id: string;
      selector?: string | null;
      text_quote?: string | null;
      captured_at: string;
    };

export interface EvidenceAnchor {
  id: string;
  workspace_id: string;
  document_id: string | null;
  version_id: string | null;
  chunk_id: string | null;
  source_item_id: string | null;
  anchor_type: EvidenceLocator["type"];
  locator: EvidenceLocator;
  quote: string;
  content_hash: string;
  source_uri_snapshot: string | null;
  source_quality: number | null;
  validation_state: EvidenceValidationState;
  created_by_type: OriginType;
  created_by_id: string | null;
  supersedes_anchor_id: string | null;
  created_at: string;
}

export interface ProvenanceNode {
  id: string;
  layer: TraceLayer;
  node_type: string;
  backing_type: string;
  backing_id: string;
  label: string;
  occurred_at: string | null;
  confidence: number | null;
  review_status: ReviewStatus | null;
  validation_status: ValidationStatus | EvidenceValidationState | null;
  properties: Record<string, unknown>;
}

export interface ProvenanceEdge {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: TraceRelationType;
  rationale: string | null;
  confidence: number | null;
  review_status: ReviewStatus;
  validation_status: ValidationStatus;
  origin_type: OriginType;
  evidence_anchor_ids: string[];
  version_no: number;
  model_metadata: Record<string, unknown>;
}

export interface ProvenanceCluster {
  id: string;
  layer: TraceLayer;
  label: string;
  node_ids: string[];
  count: number;
}

export interface ProvenanceGraphResponse {
  nodes: ProvenanceNode[];
  edges: ProvenanceEdge[];
  clusters: ProvenanceCluster[];
  graph_version: string;
  degraded: boolean;
  degraded_reason: string | null;
  total_nodes: number;
  returned_nodes: number;
  has_more: boolean;
  next_cursor: string | null;
}

export interface TraceEdgeDetail extends ProvenanceEdge {
  review_history: Array<Record<string, unknown>>;
  evidence: EvidenceAnchor[];
}

export interface TraceEdgeReviewRequest {
  action: ReviewAction;
  version_no: number;
  reviewer_id: string;
  note?: string;
}

export interface TraceEdgeReviewResponse {
  edge: ProvenanceEdge;
  previous_review_status: ReviewStatus;
  reviewed_at: string;
}

export interface ConclusionCreate {
  conclusion_type: "investment" | "research";
  conclusion_subtype?: string | null;
  title: string;
  body: string;
  stance?: string | null;
  scope?: Record<string, unknown>;
  valid_from?: string | null;
  valid_to?: string | null;
  as_of?: string | null;
  confidence: number;
  review_status?: ReviewStatus;
  validation_status?: ValidationStatus;
  origin_type?: OriginType;
  model_metadata?: Record<string, unknown>;
  source_object_type?: string | null;
  source_object_id?: string | null;
}

export interface Conclusion extends ConclusionCreate {
  id: string;
  workspace_id: string;
  version_no: number;
  supersedes_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProvenanceOverviewFilters {
  limit?: number;
  layer?: TraceLayer;
  display_status?: string;
  min_confidence?: number;
  conclusion_type?: "investment" | "research";
  cursor?: string;
}

export interface ProvenanceRebuildResponse {
  job_id: string;
  status: string;
  reused: boolean;
}

export interface ProvenanceJob {
  id: string;
  workspace_id: string;
  status: string;
  progress: number;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}
