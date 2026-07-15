import { apiRequest } from "./client";

// --- types (mirror backend app/schemas/investment.py) ---------------------

export type InfoLayer = "primary_source" | "macro_calendar" | "news" | "opinion";
export type SourceCredibility =
  | "official"
  | "reliable_media"
  | "personal_opinion"
  | "unverified";
export type SourceLayer =
  | "primary_source"
  | "human_source"
  | "expert_opinion"
  | "news_confirmation"
  | "market_feedback";
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
  | "x_rss"
  | "x_nitter"
  | "x_brightdata"
  | "x_web"
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
  | "local_only"
  | "ignored";

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
  title_zh?: string | null;
  summary_zh?: string | null;
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
  attachments?: InvestmentAttachment[];
}

export interface InvestmentTheme {
  id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  theme_type: string;
  keywords: string[];
  entities: string[];
  tickers: string[];
  enabled: boolean;
  priority: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ThemeSourceBinding {
  id: string;
  workspace_id: string;
  theme_id: string;
  source_id: string;
  source_layer: SourceLayer;
  priority: number;
  collector_type?: string | null;
  coverage_notes?: string | null;
  enabled: boolean;
}

export interface InvestmentAttachment {
  title: string;
  url: string;
  content_type?: string | null;
  text_excerpt?: string | null;
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

export interface XCollectorState {
  collector_id: string;
  version: string;
  login_status: "uninitialized" | "ready" | "auth_required" | "challenge_required";
  queue_size: number;
  last_success_at?: string | null;
  last_error?: string | null;
  heartbeat_at: string;
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

export interface InvestmentFact {
  id: string;
  workspace_id: string;
  source_item_id: string;
  watchlist_id?: string | null;
  fact_text: string;
  fact_text_zh?: string | null;
  fact_type: string;
  entities: string[];
  evidence_url?: string | null;
  evidence_excerpt: string;
  evidence_timestamp?: number | null;
  confidence: number;
  verification_status: VerificationStatus;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface InvestmentSignal {
  id: string;
  workspace_id: string;
  watchlist_id?: string | null;
  title: string;
  summary: string;
  signal_type: string;
  first_seen_at: string;
  last_seen_at: string;
  source_count: number;
  fact_ids: string[];
  item_ids: string[];
  confidence: number;
  status: string;
  signal_stage?: string;
  source_layers?: SourceLayer[];
  first_source_layer?: SourceLayer | null;
  first_source_id?: string | null;
  validation_state?: string;
  validation_sources?: string[];
  market_feedback?: Record<string, unknown>;
  lead_time_hours?: number | null;
  information_edge_score?: number;
  actionability?: string;
  score_breakdown?: Record<string, number>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SourceTrace {
  id: string;
  workspace_id: string;
  theme_id?: string | null;
  target_item_id: string;
  source_item_id?: string | null;
  trace_type: string;
  match_reason: string;
  matched_fact?: string | null;
  lead_time_hours?: number | null;
  confidence: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface InvestmentDashboard {
  pending_review_count: number;
  pending_claims_count: number;
  theses_challenged_count: number;
  today_primary_count: number;
  today_macro_count: number;
  untranslated_count: number;
  unextracted_count: number;
  unsignaled_count: number;
  failed_job_count: number;
}

export interface InvestmentDigest {
  counts: InvestmentDashboard;
  today_highlights: InvestmentItem[];
  pending_claims: InvestmentClaim[];
  challenged_items: InvestmentItem[];
  early_signals: InvestmentSignal[];
  pending_facts: InvestmentFact[];
}

export interface InformationEdgeDigest {
  generated_at: string;
  top_signals: InvestmentSignal[];
  source_traces: SourceTrace[];
  unvalidated_signals: InvestmentSignal[];
  stale_or_noise: InvestmentSignal[];
}

export interface InvestmentDigestSnapshot {
  id: string;
  workspace_id: string;
  watchlist_id?: string | null;
  digest_date: string;
  title: string;
  digest: InvestmentDigest;
  created_at?: string | null;
  updated_at?: string | null;
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

export interface ListFactsParams {
  workspaceId?: string;
  itemId?: string;
  sourceId?: string;
  watchlistId?: string;
  verificationStatus?: VerificationStatus;
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
  default_watchlist_ids?: string[];
  poll_interval_seconds?: number;
  enabled?: boolean;
}

export interface UpdateSourcePayload {
  name?: string;
  url?: string;
  config?: Record<string, unknown>;
  default_info_layer?: InfoLayer;
  default_watchlist_ids?: string[];
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

export interface CreateThemePayload {
  workspace_id?: string;
  name: string;
  description?: string;
  theme_type?: string;
  keywords?: string[];
  entities?: string[];
  tickers?: string[];
  enabled?: boolean;
  priority?: string;
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

  // macro calendar
  listMacroEvents(params: {
    workspaceId?: string;
    days?: number;
    importance?: Importance;
    limit?: number;
  } = {}): Promise<InvestmentItem[]> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      days: params.days ?? 30,
      importance: params.importance,
      limit: params.limit ?? 100,
    });
    return apiRequest(`/investment/macro-events${q}`);
  },

  // daily digest (aggregate view)
  getDigest(params: { workspaceId?: string; watchlistId?: string } = {}): Promise<InvestmentDigest> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      watchlist_id: params.watchlistId,
    });
    return apiRequest(`/investment/digest${q}`);
  },
  listDigestSnapshots(params: {
    workspaceId?: string;
    watchlistId?: string;
    limit?: number;
  } = {}): Promise<InvestmentDigestSnapshot[]> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      watchlist_id: params.watchlistId,
      limit: params.limit ?? 20,
    });
    return apiRequest(`/investment/digest/snapshots${q}`);
  },
  createDigestSnapshot(params: {
    workspaceId?: string;
    watchlistId?: string;
  } = {}): Promise<InvestmentDigestSnapshot> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      watchlist_id: params.watchlistId,
    });
    return apiRequest(`/investment/digest/snapshots${q}`, { method: "POST" });
  },

  // information edge
  getInformationEdge(params: {
    workspaceId?: string;
    themeId?: string;
    limit?: number;
  } = {}): Promise<InformationEdgeDigest> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      theme_id: params.themeId,
      limit: params.limit ?? 20,
    });
    return apiRequest(`/investment/information-edge${q}`);
  },
  listThemes(workspaceId = WS): Promise<InvestmentTheme[]> {
    return apiRequest(`/investment/themes?workspace_id=${workspaceId}`);
  },
  createTheme(payload: CreateThemePayload): Promise<InvestmentTheme> {
    return apiRequest("/investment/themes", { method: "POST", body: payload });
  },
  listThemeSources(themeId: string, workspaceId = WS): Promise<ThemeSourceBinding[]> {
    const q = buildQuery({ workspace_id: workspaceId });
    return apiRequest(`/investment/themes/${themeId}/sources${q}`);
  },
  listSourceTraces(params: {
    workspaceId?: string;
    themeId?: string;
    targetItemId?: string;
    limit?: number;
  } = {}): Promise<SourceTrace[]> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      theme_id: params.themeId,
      target_item_id: params.targetItemId,
      limit: params.limit ?? 50,
    });
    return apiRequest(`/investment/source-traces${q}`);
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
  listItemFacts(id: string): Promise<InvestmentFact[]> {
    return apiRequest(`/investment/items/${id}/facts`);
  },
  listFacts(params: ListFactsParams = {}): Promise<InvestmentFact[]> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      item_id: params.itemId,
      source_id: params.sourceId,
      watchlist_id: params.watchlistId,
      verification_status: params.verificationStatus,
      limit: params.limit ?? 100,
    });
    return apiRequest(`/investment/facts${q}`);
  },
  listSignals(params: {
    workspaceId?: string;
    watchlistId?: string;
    status?: string;
    limit?: number;
  } = {}): Promise<InvestmentSignal[]> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      watchlist_id: params.watchlistId,
      status: params.status,
      limit: params.limit ?? 20,
    });
    return apiRequest(`/investment/signals${q}`);
  },
  refreshSignals(params: { workspaceId?: string; watchlistId?: string } = {}): Promise<InvestmentSignal[]> {
    const q = buildQuery({
      workspace_id: params.workspaceId ?? WS,
      watchlist_id: params.watchlistId,
    });
    return apiRequest(`/investment/signals/refresh${q}`, { method: "POST" });
  },
  classifyItem(id: string): Promise<InvestmentItem> {
    return apiRequest(`/investment/items/${id}/classify`, { method: "POST" });
  },
  translateItems(workspaceId = WS, limit = 20): Promise<{ translated: number; skipped: number }> {
    const q = buildQuery({ workspace_id: workspaceId, limit });
    return apiRequest(`/investment/items/translate${q}`, { method: "POST" });
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
  listWatchlistSources(id: string): Promise<InvestmentSource[]> {
    return apiRequest(`/investment/watchlist/${id}/sources`);
  },
  bindWatchlistSource(watchlistId: string, sourceId: string): Promise<InvestmentSource> {
    return apiRequest(`/investment/watchlist/${watchlistId}/sources/${sourceId}`, {
      method: "POST",
    });
  },
  unbindWatchlistSource(watchlistId: string, sourceId: string): Promise<InvestmentSource> {
    return apiRequest(`/investment/watchlist/${watchlistId}/sources/${sourceId}`, {
      method: "DELETE",
    });
  },

  // sources
  listSources(workspaceId = WS): Promise<InvestmentSource[]> {
    return apiRequest(`/investment/sources?workspace_id=${workspaceId}`);
  },
  createSource(payload: CreateSourcePayload): Promise<InvestmentSource> {
    return apiRequest("/investment/sources", { method: "POST", body: payload });
  },
  createDefaultSources(): Promise<InvestmentSource[]> {
    return apiRequest("/investment/sources/defaults", { method: "POST" });
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
  getXCollectorState(collectorId: string): Promise<XCollectorState | null> {
    return apiRequest(
      `/investment/x-collector/state?collector_id=${encodeURIComponent(collectorId)}`,
    );
  },
  listXCollectorStates(): Promise<XCollectorState[]> {
    return apiRequest("/investment/x-collector/states");
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
  setClaimStatus(
    id: string,
    payload: {
      verification_status: VerificationStatus;
      verification_summary?: string;
      thesis_id?: string;
    },
  ): Promise<InvestmentClaim> {
    return apiRequest(`/investment/claims/${id}/status`, { method: "POST", body: payload });
  },
  verifyClaim(id: string): Promise<InvestmentClaim> {
    return apiRequest(`/investment/claims/${id}/verify`, { method: "POST" });
  },
};
