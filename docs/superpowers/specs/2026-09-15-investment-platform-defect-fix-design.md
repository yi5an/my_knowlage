# Investment Opportunity Discovery Defect Fix Design

**Date:** 2026-09-15  
**Status:** Approved direction (方案 A)  
**Scope:** Existing KnowPilot investment workspace

## Goal

把现有投资情报工作区从“信息素材台”提升为可日常使用的投资机会发现闭环：用户能看到数据是否新鲜，理解后台是否健康，获得可解释的机会候选和账号推荐，并能把信号转化为可验证假设。

本次采用增量修复，不重写既有数据库模型，不改变 X / YouTube 原文保存和内部追踪语义。

## Product principles

1. **新鲜度先于数量**：过期数据必须显式标记，不能继续显示“过去 24 小时”。
2. **机会必须可验证**：没有唯一标的、证据和失效条件时不生成机会候选。
3. **原文可追溯**：所有翻译、信号、机会和人物影响结果都保留原始链接或证据引用。
4. **不把相关性冒充因果性**：人物影响和市场反应显示样本量、并发事件和不确定性。
5. **失败可解释、可恢复**：后台失败任务暴露原因，并支持幂等重试。
6. **新用户可冷启动**：账号推荐不依赖用户先配置人物源；种子目录是受控、可审计的。

## Scope and architecture

### P0 — first release

#### 1. Data freshness and source health

Add a read-only workspace health projection built from `InvestmentSource`, `TaskJob`, and recent `InvestmentItem` rows. Each source reports:

- enabled state;
- last successful fetch time;
- last failed fetch time and sanitized error message;
- consecutive failures;
- newest item time and age in hours;
- health state: `healthy`, `delayed`, `stale`, or `failed`.

The dashboard response will include an aggregate freshness state and the UI will show a warning when the newest successful source data is older than the configured threshold. The source list will show per-source health. Thresholds are configuration values with safe defaults (24 hours for delayed, 48 hours for stale).

#### 2. Signal to opportunity candidates

Add a deterministic opportunity candidate builder that consumes active signals. It may create a candidate only when:

- signal confidence and source evidence meet configurable minimums;
- a unique ticker/ETF mapping can be established from the signal, theme, or watchlist;
- market reaction is known;
- evidence references, catalyst, expected case, market case, impact path, risks, invalidation conditions, and next action can be populated.

Candidate creation is idempotent by workspace + signal. Candidates remain reviewable hypotheses, never direct buy/sell advice. The API exposes the reason when a signal is gated (`missing_asset_mapping`, `market_reaction_unknown`, `insufficient_evidence`, etc.). The homepage will distinguish “机会候选” from “待补充映射”。

#### 3. Account recommendation cold start

Add a versioned, code-owned seed catalog for high-signal X, YouTube, and institutional accounts. Seeds are inserted only when a workspace has no matching recommendation/source and are marked as `seeded` in metadata. The existing evidence and follow flow remains unchanged. Each recommendation includes:

- platform and handle;
- learning/follow reason;
- theme coverage;
- source quality;
- expected information edge;
- caveat that it is an internal KnowPilot subscription.

External search remains optional; no search key means the seed catalog still renders.

#### 4. Task recovery center

Add read-only task health summaries and a safe retry endpoint for failed investment jobs. Retry must:

- be workspace-scoped;
- create at most one pending/running job for the same logical target;
- preserve the original failure record;
- return the new job id and status;
- reject unsupported job types explicitly.

The UI will show pending/running/failed counts, recent error summaries, and retry buttons. It will not expose secrets from task input or error text.

### P1 — second release

#### 5. Person impact usability

Complete person-to-asset mapping and sample readiness. Impact profiles only show directional summaries after at least five valid, non-excluded events; otherwise the page stays descriptive and highlights uncertainty.

#### 6. Personal investment context

Provide a compact first-run form for markets, horizon, focus themes, liquidity preference, and risk notes. Context affects opportunity ranking and account recommendation explanations, but never silently deletes data.

#### 7. Signal de-duplication

Improve semantic clustering so the same event across source names and fact types becomes one signal with “new information” versus “repeat confirmation”. Preserve trace edges to all source facts.

## API changes

The following additive endpoints/contracts are planned:

- `GET /api/v1/investment/health` — workspace aggregate and per-source health;
- `GET /api/v1/investment/tasks/health` — investment task counts and recent failures;
- `POST /api/v1/investment/tasks/{job_id}/retry` — idempotent retry;
- `POST /api/v1/investment/opportunities/refresh` — build candidates from active signals;
- existing `GET /opportunities`, `GET /account-recommendations`, and `GET /dashboard` gain additive fields only.

All new responses use Pydantic schemas. Existing clients remain compatible because new fields are optional or additive.

## Data flow

```text
source poll -> investment_item -> translation/fact extraction
                                    -> signal refresh + de-duplication
                                    -> gated opportunity candidate
                                    -> hypothesis verification / market feedback
```

Health is computed alongside this flow from durable source and task timestamps; it does not make external requests during a read-only page load.

## Error handling

- Missing API keys or unavailable providers produce explicit source/task errors.
- Translation or extraction failure never overwrites original text.
- Opportunity generation skips unsafe mappings and records a stable reason.
- Retry endpoints never mutate completed history and never enqueue duplicates.
- Frontend renders partial failures per section and gives a retry action.

## Testing and acceptance

Backend:

- unit tests for freshness thresholds, source state aggregation, retry idempotency, seed insertion, opportunity gating, and deduplication;
- API tests for all new endpoints and additive response fields;
- full `pytest`, `ruff check .`, and `mypy app`.

Frontend:

- tests for stale-data banner, task health panel, opportunity empty/gated states, and seeded recommendation cards;
- `npm run lint`, `npm run test -- --run`, and `npm run build`.

Remote acceptance:

- migration upgrade succeeds;
- backend/frontend containers are healthy;
- `/api/v1/health`, `/api/v1/investment/health`, `/api/v1/investment/tasks/health`, `/api/v1/investment/dashboard`, and `/api/v1/investment/opportunities` return 200;
- frontend `/` and `/investment` return the new SPA bundle;
- no recent backend/frontend `ERROR`, `Traceback`, or `FATAL` logs.

## Known limitations

The seed catalog is a product-controlled starting set, not a claim that an account is profitable or authoritative. Market data availability and X/YouTube provider reliability remain external dependencies. The system surfaces opportunities for research and hypothesis verification; it does not provide personalized financial advice or execute trades.
