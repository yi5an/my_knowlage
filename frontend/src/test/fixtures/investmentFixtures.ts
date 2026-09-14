import type {
  AccountRecommendation,
  InvestmentDashboard,
  InvestmentItem,
  InvestmentSignal,
  OpportunityCandidate,
  PersonImpactEvent,
  PersonImpactProfile,
} from "../../services/investmentApi";

type ResponseBody = InvestmentDashboard | InvestmentItem[] | InvestmentSignal[] | OpportunityCandidate[];
type FetchResponder = (url: string, init?: RequestInit) => Promise<Response>;

export type InvestmentFixtureOptions = {
  opportunityCount?: number;
  itemCount?: number;
  signalCount?: number;
  dashboard?: Partial<InvestmentDashboard>;
  failures?: Array<"dashboard" | "items" | "signals" | "opportunities">;
};

const emptyDashboard: InvestmentDashboard = {
  pending_review_count: 0,
  pending_claims_count: 0,
  theses_challenged_count: 0,
  today_primary_count: 0,
  today_macro_count: 0,
  untranslated_count: 0,
  unextracted_count: 0,
  unsignaled_count: 0,
  failed_job_count: 0,
};

export const recommendationFixture = (
  overrides: Partial<AccountRecommendation> = {},
): FetchResponder => {
  const recommendation: AccountRecommendation = {
    id: "rec_fixture",
    workspace_id: "ws_default",
    person_source_id: "person_fixture",
    platform: "x",
    handle: "signal_hunter",
    display_name: "Signal Hunter",
    role_type: "analyst",
    theme_ids: ["theme_ai"],
    recommendation_label: "值得关注",
    reason: "持续提供可验证的一手线索",
    score_breakdown: { theme_relevance: 0.9 },
    sample_count: 12,
    evidence_count: 8,
    status: "new",
    ...overrides,
  };
  return async (url: string): Promise<Response> => {
    if (url.includes("/follow")) {
      return new Response(
        JSON.stringify({
          id: "source_followed",
          workspace_id: recommendation.workspace_id,
          source_type: recommendation.platform === "youtube" ? "rss" : "x_web",
          name: recommendation.display_name ?? recommendation.handle,
          url: `https://${recommendation.platform}.com/${recommendation.handle}`,
          config: { username: recommendation.handle },
          default_info_layer: "opinion",
          default_watchlist_ids: [],
          poll_interval_seconds: 3600,
          enabled: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(JSON.stringify([recommendation]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
};

export const personImpactFixture = (
  overrides: Partial<PersonImpactProfile> = {},
): FetchResponder => {
  const profile: PersonImpactProfile = {
    person_source_id: "person_fixture",
    sample_count: 12,
    valid_sample_count: 10,
    excluded_sample_count: 2,
    sample_sufficient: true,
    positive_event_count: 6,
    negative_event_count: 3,
    neutral_event_count: 1,
    hit_rate: 0.6,
    average_lead_time_hours: 18,
    average_excess_return_1d: 0.023,
    stability_score: 0.72,
    uncertainty: "样本量有限",
    ...overrides,
  };
  const event = personImpactEventFixture({
    person_source_id: profile.person_source_id,
    workspace_id: "ws_default",
  });
  return async (url: string): Promise<Response> => {
    const body = url.includes("impact-profile") ? profile : [event];
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
};

export const investmentFetchFixture = (options: InvestmentFixtureOptions = {}) => {
  const opportunityCount = options.opportunityCount ?? 2;
  const itemCount = options.itemCount ?? 2;
  const signalCount = options.signalCount ?? 2;
  const failures = new Set(options.failures ?? []);

  const dashboard: InvestmentDashboard = { ...emptyDashboard, ...options.dashboard };
  const items: InvestmentItem[] = Array.from({ length: itemCount }, (_, index) => ({
    id: `item_fixture_${index}`,
    workspace_id: "ws_default",
    dedupe_key: `item_fixture_${index}`,
    title: `Investment intelligence ${index + 1}`,
    title_zh: `最新情报 ${index + 1}`,
    source_url: `https://example.com/items/${index + 1}`,
    source_name: index % 2 === 0 ? "X / source" : "SEC filing",
    info_layer: index % 2 === 0 ? "opinion" : "primary_source",
    source_credibility: index % 2 === 0 ? "personal_opinion" : "official",
    published_at: "2026-09-14T08:00:00Z",
    summary: `Evidence summary ${index + 1}`,
    summary_zh: `证据摘要 ${index + 1}`,
    importance: index === 0 ? "high" : "medium",
    impact_direction: index === 0 ? "positive" : "neutral",
    impact_horizon: "short",
    thesis_impact: index === 0 ? "supports" : "unknown",
    action_status: "pending_review",
  }));
  const signals: InvestmentSignal[] = Array.from({ length: signalCount }, (_, index) => ({
    id: `signal_fixture_${index}`,
    workspace_id: "ws_default",
    title: `正在发生 ${index + 1}`,
    summary: `Signal summary ${index + 1}`,
    signal_type: "capex_signal",
    first_seen_at: "2026-09-13T08:00:00Z",
    last_seen_at: "2026-09-14T08:00:00Z",
    source_count: 2,
    fact_ids: [`fact_${index}`],
    item_ids: [`item_fixture_${index}`],
    confidence: 0.82,
    status: "tracking",
  }));
  const opportunities: OpportunityCandidate[] = Array.from(
    { length: opportunityCount },
    (_, index) => ({
      id: `opportunity_fixture_${index}`,
      workspace_id: "ws_default",
      title: `机会线索 ${index + 1}`,
      asset_symbols: ["NVDA"],
      signal_id: `signal_fixture_${index % Math.max(signalCount, 1)}`,
      opportunity_type: "catalyst",
      change_summary: "需求与供给出现新的变化",
      expected_case: "预期盈利增速高于市场一致预期",
      market_case: "市场尚未充分定价该变化",
      impact_path: "需求变化 → 收入预期 → 盈利重估",
      catalyst: "下一次业绩更新或供应链确认",
      risk_flags: ["宏观波动"],
      invalidation_conditions: ["后续数据不支持需求判断"],
      next_action: "补充独立来源并建立验证任务",
      evidence_refs: [`item_fixture_${index % Math.max(itemCount, 1)}`],
      confidence: 0.78,
      status: "new",
      priority: "high_priority_research",
      market_reaction_state: "尚未充分反应",
      score_breakdown: { validation: 0.7 },
      outcome: {},
    }),
  );

  return async (url: string): Promise<Response> => {
    const value = String(url);
    const endpoint = value.includes("/investment/dashboard")
      ? "dashboard"
      : value.includes("/investment/opportunities")
        ? "opportunities"
        : value.includes("/investment/signals")
          ? "signals"
          : value.includes("/investment/items")
            ? "items"
            : null;
    if (endpoint && failures.has(endpoint)) {
      return new Response(JSON.stringify({ detail: `fixture ${endpoint} failed` }), { status: 503 });
    }
    const bodies: Record<string, ResponseBody> = { dashboard, items, signals, opportunities };
    return endpoint
      ? new Response(JSON.stringify(bodies[endpoint]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      : new Response("not found", { status: 404 });
  };
};

export const personImpactEventFixture = (
  overrides: Partial<PersonImpactEvent> = {},
): PersonImpactEvent => ({
  id: "impact_event_fixture",
  workspace_id: "ws_default",
  person_source_id: "person_fixture",
  source_item_id: "item_fixture_0",
  symbol: "NVDA",
  benchmark_symbol: "SPY",
  event_at: "2026-09-13T08:00:00Z",
  event_cluster_id: "cluster_fixture",
  window_overlap: false,
  event_status: "computed",
  data_quality: "complete",
  windows: { "1d": { excess_return: 0.02 } },
  concurrent_events: [],
  confidence: 0.8,
  ...overrides,
});
