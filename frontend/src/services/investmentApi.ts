import { apiRequest } from "./client";

// --- types (mirror backend app/schemas/investment.py) ---------------------

export type InfoLayer = "primary_source" | "macro_calendar" | "news" | "opinion";
export type SourceCredibility =
  | "official"
  | "reliable_media"
  | "personal_opinion"
  | "unverified";
export type ImpactDirection = "positive" | "negative" | "neutral" | "uncertain";
export type ImpactHorizon = "short" | "mid" | "long" | "unknown";
export type ThesisImpact =
  | "supports"
  | "weakens"
  | "contradicts"
  | "unrelated"
  | "unknown";
export type ActionStatus =
  | "pending_review"
  | "tracking"
  | "ignored"
  | "researched"
  | "archived";
export type Importance = "low" | "medium" | "high";
export type SourceType =
  | "rss"
  | "sec_edgar"
  | "federal_reserve_rss"
  | "bls"
  | "fred"
  | "hkex"
  | "cninfo"
  | "manual";
export type VerificationStatus =
  | "pending"
  | "verifying"
  | "verified"
  | "refuted"
  | "local_only";

export interface InvestmentItem {
  id: string;
  workspace_id: string;
  document_id?: string | null;
  source_id?: string | null;
  dedupe_key: string;
  title: string;
  source_url?: string | null;
  source_name?: string | null;
  info_layer: InfoLayer;
  source_credibility: SourceCredibility;
  published_at?: string | null;
  event_at?: string | null;
  summary?: string | null;
  importance: Importance;
  impact_direction: ImpactDirection;
  impact_horizon: ImpactHorizon;
  thesis_impact: ThesisImpact;
  action_status: ActionStatus;
  review_at?: string | null;
  suggested_importance?: string | null;
  suggested_impact_direction?: string | null;
  suggested_impact_horizon?: string | null;
  suggested_thesis_impact?: string | null;
  classification_reason?: string | null;
}

export interface InvestmentWatchlist {
  id: string;
  workspace_id: string;
  name: string;
  watch_type: string;
  entity_id?: string | null;
  ticker?: string | null;
  exchange?: string | null;
  keywords: string[];
  importance: Importance;
  notes?: string | null;
  enabled: boolean;
}

export interface InvestmentSource {
  id: string;
  workspace_id: string;
  source_type: SourceType;
  name: string;
  url?: string | null;
  config: Record<string, unknown>;
  default_info_layer: InfoLayer;
  default_watchlist_ids: string[];
  poll_interval_seconds: number;
  last_polled_at?: string | null;
  next_poll_at?: string | null;
  last_error?: string | null;
  enabled: boolean;
}

export interface InvestmentThesis {
  id: string;
  workspace_id: string;
  watchlist_id?: string | null;
  title: string;
  body?: string | null;
  status: string;
  confidence: string;
  last_reviewed_at?: string | null;
}

export interface InvestmentClaim {
  id: string;
  workspace_id: string;
  source_item_id?: string | null;
  watchlist_id?: string | null;
  thesis_id?: string | null;
  claim_text: string;
  required_evidence: string[];
  verification_status: VerificationStatus;
  verification_summary?: string | null;
  evidence_doc_ids: string[];
}

export interface InvestmentDashboard {
  pending_review_count: number;
  pending_claims_count: number;
  theses_challenged_count: number;
  today_primary_count: number;
  today_macro_count: number;
}

export interface InvestmentFetchJob {
  id: string;
  source_id?: string | null;
  workspace_id: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  items_seen: number;
  items_created: number;
  items_skipped: number;
  last_error?: string | null;
}

// --- params / payloads ----------------------------------------------------

export interface ListItemsParams {
  workspaceId?: string;
  infoLayer?: InfoLayer;
  actionStatus?: ActionStatus;
  watchlistId?: string;
  sourceId?: string;
  limit?: number;
}

export interface CreateItemPayload {
  workspace_id?: string;
  title: string;
  info_layer?: InfoLayer;
  source_credibility?: SourceCredibility;
  source_url?: string;
  source_name?: string;
  summary?: string;
  importance?: Importance;
  impact_direction?: ImpactDirection;
  impact_horizon?: ImpactHorizon;
  thesis_impact?: ThesisImpact;
  action_status?: ActionStatus;
}

export interface UpdateItemPayload {
  title?: string;
  summary?: string;
  importance?: Importance;
  impact_direction?: ImpactDirection;
  impact_horizon?: ImpactHorizon;
  thesis_impact?: ThesisImpact;
  action_status?: ActionStatus;
}

export interface CreateWatchlistPayload {
  workspace_id?: string;
  name: string;
  watch_type?: string;
  ticker?: string;
  exchange?: string;
  keywords?: string[];
  importance?: Importance;
  notes?: string;
}

export interface UpdateWatchlistPayload {
  name?: string;
  watch_type?: string;
  ticker?: string;
  exchange?: string;
  keywords?: string[];
  importance?: Importance;
  notes?: string;
  enabled?: boolean;
}

export interface CreateSourcePayload {
  workspace_id?: string;
  source_type: SourceType;
  name: string;
  url?: string;
  config?: Record<string, unknown>;
  default_info_layer?: InfoLayer;
  poll_interval_seconds?: number;
  enabled?: boolean;
}

export interface UpdateSourcePayload {
  name?: string;
  url?: string;
  config?: Record<string, unknown>;
  default_info_layer?: InfoLayer;
  poll_interval_seconds?: number;
  enabled?: boolean;
}

export interface CreateThesisPayload {
  workspace_id?: string;
  watchlist_id?: string;
  title: string;
  body?: string;
  status?: string;
  confidence?: string;
}

export interface CreateClaimPayload {
  workspace_id?: string;
  source_item_id?: string;
  watchlist_id?: string;
  thesis_id?: string;
  claim_text: string;
  required_evidence?: string[];
}

// --- API ------------------------------------------------------------------

const WS = "ws_default";

function buildQuery(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const investmentApi = {
  // dashboard
  getDashboard(workspaceId = WS): Promise<InvestmentDashboard> {
    return apiRequest(`/investment/dashboard?workspace_id=${workspaceId}`);
  },

  // items
  listItems(params: ListItemsParams = {}): Promise<InvestmentItem[]> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      info_layer: params.infoLayer,
      action_status: params.actionStatus,
      watchlist_id: params.watchlistId,
      source_id: params.sourceId,
      limit: params.limit,
    });
    return apiRequest(`/investment/items${q}`);
  },
  createItem(payload: CreateItemPayload): Promise<InvestmentItem> {
    return apiRequest("/investment/items", { method: "POST", body: payload });
  },
  updateItem(id: string, payload: UpdateItemPayload): Promise<InvestmentItem> {
    return apiRequest(`/investment/items/${id}`, { method: "PATCH", body: payload });
  },

  // watchlist
  listWatchlist(workspaceId = WS): Promise<InvestmentWatchlist[]> {
    return apiRequest(`/investment/watchlist?workspace_id=${workspaceId}`);
  },
  createWatchlist(payload: CreateWatchlistPayload): Promise<InvestmentWatchlist> {
    return apiRequest("/investment/watchlist", { method: "POST", body: payload });
  },
  updateWatchlist(id: string, payload: UpdateWatchlistPayload): Promise<InvestmentWatchlist> {
    return apiRequest(`/investment/watchlist/${id}`, { method: "PATCH", body: payload });
  },

  // sources
  listSources(workspaceId = WS): Promise<InvestmentSource[]> {
    return apiRequest(`/investment/sources?workspace_id=${workspaceId}`);
  },
  createSource(payload: CreateSourcePayload): Promise<InvestmentSource> {
    return apiRequest("/investment/sources", { method: "POST", body: payload });
  },
  updateSource(id: string, payload: UpdateSourcePayload): Promise<InvestmentSource> {
    return apiRequest(`/investment/sources/${id}`, { method: "PATCH", body: payload });
  },
  pollSource(id: string): Promise<{ job_id: string; status: string }> {
    return apiRequest(`/investment/sources/${id}/poll`, { method: "POST" });
  },
  getFetchJob(id: string): Promise<InvestmentFetchJob> {
    return apiRequest(`/investment/jobs/${id}`);
  },

  // theses
  listTheses(workspaceId = WS, watchlistId?: string): Promise<InvestmentThesis[]> {
    const q = buildQuery({ workspace_id: workspaceId, watchlist_id: watchlistId });
    return apiRequest(`/investment/theses${q}`);
  },
  createThesis(payload: CreateThesisPayload): Promise<InvestmentThesis> {
    return apiRequest("/investment/theses", { method: "POST", body: payload });
  },
  updateThesis(id: string, payload: Partial<CreateThesisPayload>): Promise<InvestmentThesis> {
    return apiRequest(`/investment/theses/${id}`, { method: "PATCH", body: payload });
  },

  // claims
  listClaims(
    workspaceId = WS,
    filters: { watchlistId?: string; verificationStatus?: VerificationStatus } = {},
  ): Promise<InvestmentClaim[]> {
    const q = buildQuery({
      workspace_id: workspaceId,
      watchlist_id: filters.watchlistId,
      verification_status: filters.verificationStatus,
    });
    return apiRequest(`/investment/claims${q}`);
  },
  createClaim(payload: CreateClaimPayload): Promise<InvestmentClaim> {
    return apiRequest("/investment/claims", { method: "POST", body: payload });
  },
  updateClaim(
    id: string,
    payload: Partial<{
      claim_text: string;
      required_evidence: string[];
      verification_status: VerificationStatus;
      verification_summary: string;
      evidence_doc_ids: string[];
    }>,
  ): Promise<InvestmentClaim> {
    return apiRequest(`/investment/claims/${id}`, { method: "PATCH", body: payload });
  },
};
