# Investment Platform Defect Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复投资平台的核心 P0 缺陷，使数据新鲜度、后台任务、机会候选和账号推荐形成可验证的日常工作流。

**Architecture:** 在现有 FastAPI investment service 和 React 页面上增量添加 read-only health projections、幂等任务重试、受控账号种子和 signal-to-opportunity builder。所有接口先定义 Pydantic schemas，再接 service 和 UI；不改原文、现有任务历史或 X/YouTube 追踪语义。

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, React, TypeScript, Ant Design, Vitest.

---

### Task 1: Investment health domain schemas and service

**Files:**
- Create: `backend/app/services/investment/health.py`
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_investment_health.py`

- [ ] **Step 1: Write failing tests** for source states (`healthy`, `delayed`, `stale`, `failed`), aggregate freshness, and sanitized failure messages.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Add Pydantic response schemas and pure health aggregation helpers.**
- [ ] **Step 4: Implement SQLAlchemy projection over sources, task jobs, and latest items without external requests.**
- [ ] **Step 5: Run focused tests and commit `feat: add investment source health projection`.

### Task 2: Health and task recovery APIs

**Files:**
- Modify: `backend/app/api/v1/investment.py`
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_investment_api.py`

- [ ] **Step 1: Add failing API tests for `GET /health`, `GET /tasks/health`, and `POST /tasks/{job_id}/retry`.**
- [ ] **Step 2: Implement workspace-scoped health and task summary methods.**
- [ ] **Step 3: Implement retry allowlist for `investment_fetch`, `x_web_collect`, `investment_translation`, `investment_fact_extract`, and `investment_classification`; preserve original jobs and deduplicate pending/running jobs.**
- [ ] **Step 4: Return sanitized recent failures with no secret-bearing input.**
- [ ] **Step 5: Run API tests and commit `feat: add investment task health and retry APIs`.

### Task 3: Seed account recommendation catalog

**Files:**
- Create: `backend/app/services/investment/account_seeds.py`
- Modify: `backend/app/services/investment/account_recommendation.py`
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_investment_account_recommendations.py`

- [ ] **Step 1: Add failing tests proving empty workspaces receive stable X, YouTube, and institution seed recommendations, while existing recommendations are not duplicated.**
- [ ] **Step 2: Define a versioned seed catalog with conservative descriptions and theme metadata.**
- [ ] **Step 3: Insert only missing workspace recommendations, mark metadata as seeded, and keep follow behavior unchanged.**
- [ ] **Step 4: Ensure refresh and list paths call seed initialization even when external search is unavailable.**
- [ ] **Step 5: Run focused tests and commit `feat: add cold-start account recommendations`.

### Task 4: Deterministic signal-to-opportunity refresh

**Files:**
- Modify: `backend/app/services/investment/opportunity.py`
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/api/v1/investment.py`
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_investment_opportunity.py`
- Test: `backend/tests/test_investment_api.py`

- [ ] **Step 1: Add failing tests for candidate creation from a uniquely mapped signal, idempotency, and gated reasons for missing mapping/market reaction.**
- [ ] **Step 2: Add a refresh report schema containing created count, skipped count, and stable skip reasons.**
- [ ] **Step 3: Implement conservative refresh that only uses existing signal evidence and explicit watchlist/theme tickers; never invents tickers.**
- [ ] **Step 4: Add `POST /investment/opportunities/refresh` and preserve existing manual promotion endpoint.**
- [ ] **Step 5: Run focused tests and commit `feat: refresh investment opportunity candidates`.

### Task 5: Frontend health and actionable empty states

**Files:**
- Modify: `frontend/src/services/investmentApi.ts`
- Modify: `frontend/src/pages/IntelligenceFlowPage.tsx`
- Modify: `frontend/src/pages/InvestmentDashboardPage.tsx`
- Modify: `frontend/src/pages/InvestmentSourcesPage.tsx`
- Create: `frontend/src/components/investment/InvestmentHealthPanel.tsx`
- Test: `frontend/src/pages/IntelligenceFlowPage.test.tsx`
- Test: `frontend/src/pages/InvestmentDashboardPage.test.tsx`
- Test: `frontend/src/components/investment/InvestmentHealthPanel.test.tsx`

- [ ] **Step 1: Add failing tests for stale-data banner, health metrics, and refresh/retry actions.**
- [ ] **Step 2: Add typed API methods and health panel.**
- [ ] **Step 3: Replace the unconditional “过去 24 小时 · 自动更新” copy with actual freshness state.**
- [ ] **Step 4: Show gated opportunity counts and next actions when no candidates exist.**
- [ ] **Step 5: Run frontend focused tests, lint, and build; commit `feat: expose investment health in workspace UI`.

### Task 6: Frontend account recommendations and task recovery

**Files:**
- Modify: `frontend/src/pages/AccountDiscoveryPage.tsx`
- Modify: `frontend/src/pages/InvestmentItemsPage.tsx`
- Modify: `frontend/src/services/investmentApi.ts`
- Create: `frontend/src/components/investment/TaskHealthPanel.tsx`
- Test: `frontend/src/pages/AccountDiscoveryPage.test.tsx`
- Test: `frontend/src/components/investment/TaskHealthPanel.test.tsx`

- [ ] **Step 1: Add failing tests for seed recommendations and retry button behavior.**
- [ ] **Step 2: Render seed recommendation reason and evidence labels without implying performance.**
- [ ] **Step 3: Render failed/pending task counts and call the idempotent retry API.**
- [ ] **Step 4: Keep external search warning separate from seed availability.**
- [ ] **Step 5: Run focused tests and commit `feat: add recommendation and task recovery UX`.

### Task 7: Full verification and deployment

**Files:**
- Modify: `docs/superpowers/plans/2026-09-15-investment-platform-defect-fix-plan.md` (mark completed)

- [ ] **Step 1: Run backend `pytest`, `ruff check .`, and `mypy app`.**
- [ ] **Step 2: Run frontend `npm run lint`, `npm run test -- --run`, and `npm run build`.**
- [ ] **Step 3: Inspect git diff and ensure unrelated user files stay untouched.**
- [ ] **Step 4: Sync tracked implementation files to remote while preserving remote `.env`, database, storage, and dependencies.**
- [ ] **Step 5: Run production compose rebuild and `alembic upgrade head`.**
- [ ] **Step 6: Smoke-test health, task health, dashboard, recommendations, opportunities, frontend routes, and logs.**
- [ ] **Step 7: Commit any deployment documentation updates and report evidence.**

