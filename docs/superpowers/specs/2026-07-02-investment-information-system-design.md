# KnowPilot 投资信息系统 — 设计规格 (Spec)

日期：2026-07-02
分支：`feat/investment-information-system`
状态：已确认，待实现

## 0. 目标与范围

在 KnowPilot 内新增 `investment` 模块（不从零搭建独立系统），覆盖
`doc/investment-system-docs/` 五份文档定义的全部能力（Task 1–10）：

- 真实数据源接入（SEC EDGAR / Federal Reserve RSS / 通用 RSS / BLS / FRED / HKEX / CNINFO），生产环境禁用 mock。
- 投资语义数据模型（信息分层、来源可信度、影响判断），与现有 `Document` 原文级内容职责分离。
- 异步抓取 → 去重 → 入库 → 摘要/分类流水线。
- YouTube 观点层集成（总结成功后生成 `opinion` 层 `investment_item`）。
- GLM-5.2 自动分类（写 `suggested_*` 字段，不覆盖用户确认字段）与观点验证（本地 RAG + 可选 Tavily）。
- 前端投资工作台（dashboard / watchlist / items / claims / theses / sources / calendar / digest）。

交付标准（文档任务 10）：
- 第一、第二阶段核心链路可用。
- 系统无 mock 数据。
- 所有新增内容可追溯真实 `source_url`。

## 1. 架构与放置

### 1.1 模块放置（对齐现有 `services/youtube/` 子包模式）

新增后端子包：

```
backend/app/services/investment/
  __init__.py
  models.py            # SQLAlchemy（仅当不并入 infrastructure/models.py 时；见下）
  fetchers.py          # InvestmentFetcher Protocol + 各 fetcher
  normalizers.py       # InvestmentRawItem + dedupe key
  repositories.py      # source/item/job upsert + dedupe
  service.py           # InvestmentService（API 层调用）
  fetch_job_handler.py # TaskJob handler：investment_fetch
  classifier.py        # GLM-5.2 分类（写 suggested_*）
  claim_verifier.py    # 观点验证（本地 RAG + 可选 Tavily）
  investment_dependencies.py  # FastAPI Depends 工厂
```

> 说明：本设计将 ORM 模型集中放入现有 `backend/app/infrastructure/models.py`（与全项目一致），而不是新建 `services/investment/models.py`。文档 §1 列出的 `models.py` 是子包内可选路径；为保持仓库一致性，模型统一进 `infrastructure/models.py`，子包内不再定义 ORM 模型。

### 1.2 关键结构决策：fetch job 并入 `TaskJob`（偏离文档）

文档假设一个独立的 `investment_fetch_job` 表 + 独立 APScheduler 调度器。实际代码库已具备稳健的 `TaskJob` worker（handler 注册表 `_HANDLERS` + 守护线程 `IntervalScheduler`，见 `backend/app/services/task_worker.py`）。

**决策：复用 `TaskJob`，不新建调度子系统。**

- 新增 `job_type = "investment_fetch"`，新增 `InvestmentFetchJobHandler` 注册到 `_HANDLERS`。
- `investment_source.next_poll_at` 驱动**入队**：一个轻量 `IntervalScheduler` 周期扫描到期 source，插入 `pending` `TaskJob` 行。
- 现有 `TaskJobProcessor` 执行**实际工作**（HTTP 抓取 + normalize + dedupe + persist）。

代价与补偿：

- `investment_fetch_job` **不是独立物理表，而是 `TaskJob` 的视图**（API 层按 `job_type="investment_fetch"` 查询并投影出 `items_seen/created/skipped` 等字段，这些来自 `TaskJob.output`/`error_message`）。
- 这与文档 §2.2 的字段一一对应，但物理载体是 `TaskJob`。
- 选择此偏离的理由：仓库已有两个并行的 worker 子系统会被 AGENTS.md 规则 8、9 判定为坏味道；复用更可测、更一致。

**`POST /investment/sources/{id}/poll` 语义（已与用户确认：异步 enqueue + poll）：**

1. 立即创建 `TaskJob(job_type="investment_fetch", target_type="investment_source", target_id=source_id, status="pending")`，返回 job id。
2. `TaskJobProcessor` 在下一个 tick 接管，执行真实抓取与入库。
3. 前端按返回的 job id 轮询 `GET /investment/jobs/{id}`，状态变 `succeeded/failed` 后刷新 items 列表。

## 2. 后端 — 模型与迁移

### 2.1 新增 ORM 模型（写入 `backend/app/infrastructure/models.py`）

遵循现有约定：`String(64)` 主键（应用生成 `f"{prefix}_{uuid4().hex}"`），`workspace_id` 外键，枚举存 `String`（无 DB CHECK），时间戳 mixin，JSON 列用 `JsonType`（属性名 `metadata_`/`config`/`raw_payload`）。

六个模型：

- `InvestmentWatchlist`
- `InvestmentSource`
- `InvestmentItem`
- `InvestmentThesis`
- `InvestmentClaim`
- `MacroEvent`

（`InvestmentFetchJob` 并入 `TaskJob`，不单独建表。）

字段严格按 `02-data-flow.md` §2。

### 2.2 索引与约束

- `idx_investment_item_workspace_layer_status` — `(workspace_id, info_layer, action_status)`
- `idx_investment_item_dedupe` — **唯一约束** `(workspace_id, dedupe_key)`，强制幂等
- `idx_investment_item_published` — `(workspace_id, published_at)`
- `idx_investment_source_due` — `(enabled, next_poll_at)`
- `idx_investment_claim_status` — `(workspace_id, verification_status)`
- `idx_investment_thesis_watchlist` — `(workspace_id, watchlist_id)`

### 2.3 枚举（Python `StrEnum`，DB 存 `String`）

```
InfoLayer         = primary_source | macro_calendar | news | opinion
SourceCredibility = official | reliable_media | personal_opinion | unverified
ImpactDirection   = positive | negative | neutral | uncertain
ImpactHorizon     = short | mid | long | unknown
ThesisImpact      = supports | weakens | contradicts | unrelated | unknown
ActionStatus      = pending_review | tracking | ignored | researched | archived
Importance        = low | medium | high
SourceType        = rss | sec_edgar | federal_reserve_rss | bls | fred | hkex | cninfo | manual
VerificationStatus= pending | verifying | verified | refuted | local_only
```

### 2.4 Alembic 迁移

`backend/alembic/versions/202607020001_investment_information_system.py`：建全部 investment 表 + 索引；不修改现有 `Document` 结构；`downgrade()` 完整回滚。

### 2.5 测试

`backend/tests/test_investment_models.py`：
- 能创建 watchlist / source / item / claim / thesis / macro_event。
- `investment_item.dedupe_key` 在 workspace 内唯一（重复插入抛 IntegrityError）。
- `source.next_poll_at` 可为空。

## 3. 后端 — Schema 与 API 骨架

### 3.1 `backend/app/schemas/investment.py`（Pydantic v2）

含文档 §7 列出的全部 `*Create/*Update/*Response` + `InvestmentDashboardResponse` + `InvestmentFetchJobResponse`（`TaskJob` 投影视图）。`workspace_id` 默认 `"ws_default"`。枚举用 `StrEnum`。`Literal` 约束同文档 §7。

### 3.2 `backend/app/api/v1/investment.py`

实现文档 §12 全部端点，**外加异步轮询所需**：

- `POST /investment/sources/{id}/poll` → 返回 `{"job_id": "..."}`
- `GET  /investment/jobs/{id}` → 投影为 `InvestmentFetchJobResponse`（新增，不在文档中）

在 `backend/app/api/v1/router.py` 注册：`api_router.include_router(investment.router)`。

### 3.3 测试

`backend/tests/test_investment_api.py`：
- `POST /investment/watchlist` 可创建观察对象。
- `POST /investment/items` 可手动添加投资信息。
- `GET /investment/dashboard` 返回真实 DB 统计，不返回示例数据。
- `POST /investment/sources/{id}/poll` 创建 `pending` `TaskJob`。

## 4. 后端 — Fetcher（P0）

### 4.1 依赖

`backend/pyproject.toml` 生产依赖新增：

```toml
"httpx>=0.27,<1.0",
"feedparser>=6.0,<7.0",
```

（`httpx` 现仅在 dev；上移到生产。不使用 `requests`。）

### 4.2 `backend/app/core/config.py` 新增字段（文档 §4）

```
investment_scheduler_enabled      (alias INVESTMENT_SCHEDULER_ENABLED, default True)
investment_poll_interval_seconds  (alias INVESTMENT_POLL_INTERVAL_SECONDS, default 60)
investment_http_timeout_seconds   (alias INVESTMENT_HTTP_TIMEOUT_SECONDS, default 30)
sec_user_agent                    (alias SEC_USER_AGENT, default None)
sec_max_requests_per_second       (alias SEC_MAX_REQUESTS_PER_SECOND, default 5)
fred_api_key                      (alias FRED_API_KEY, default None)
fred_base_url                     (alias FRED_BASE_URL, default https://api.stlouisfed.org/fred)
bls_api_key                       (alias BLS_API_KEY, default None)
bls_base_url                      (alias BLS_BASE_URL, default https://api.bls.gov/publicAPI/v2)
```

`.env.example` 引用但不赋值（生产无 key → `SourceConfigError`）。

### 4.3 fetcher.py

- `InvestmentFetcher(Protocol)`：`fetch(source) -> list[InvestmentRawItem]`
- `InvestmentRawItem`（frozen dataclass，文档 §8 字段）
- `SourceConfigError`
- P0 实现：`RssFetcher`、`SecEdgarFetcher`（缺 `SEC_USER_AGENT` 抛 `SourceConfigError`，按文档 §9 构造 `source_url`，过滤 forms）、`FederalReserveRssFetcher`（复用 RSS）

### 4.4 normalizers.py

`dedupe_key = sha256(source_type + stable_external_id + source_url)`（文档 §4.1）。`stable_external_id` 来源映射：SEC=accessionNumber；RSS=guid 或 link；Fed RSS=guid/link；BLS/FRED=series_id+observation_date+value；HKEX/CNINFO=announcement_id 或 PDF URL。

### 4.5 测试（本地 fixture 响应，不触网）

- `test_investment_fetchers_rss.py`：RSS entry → `InvestmentRawItem`。
- `test_investment_fetchers_sec.py`：SEC filing → `InvestmentRawItem`；缺 `SEC_USER_AGENT` 抛 `SourceConfigError`。

## 5. 后端 — 抓取服务（异步 handler）

### 5.1 `repositories.py`

- `InvestmentSourceRepository.list_due_sources()` / upsert source stats
- `InvestmentItemRepository.upsert()`（按 `(workspace_id, dedupe_key)` 幂等）
- `Document` upsert（原文层）

### 5.2 `service.py` — `InvestmentService`

文档 §11 方法：`create_watchlist/list_watchlist/create_item/list_items/update_item/create_source/list_sources/poll_source/create_claim/verify_claim/create_thesis/dashboard`。

`poll_source(source_id)`：插入 `pending` `TaskJob(job_type="investment_fetch", target_type="investment_source", target_id=source_id, input={"source_id": source_id})`，立即返回 job id。

### 5.3 `fetch_job_handler.py` — `InvestmentFetchJobHandler`

注册到 `task_worker._HANDLERS["investment_fetch"]`。`handle()`：

1. 按 `target_id` 取 source；按 `source_type` 选 fetcher。
2. fetcher.fetch() → raw items。
3. normalize → dedupe。
4. upsert `Document` + `InvestmentItem`。
5. 写 `TaskJob.output = {"items_seen","items_created","items_skipped"}`。
6. 更新 `source.last_polled_at/next_poll_at/last_error`。
7. 失败：`raise` → 由 `TaskJobProcessor._mark_failed` 记 `error_message`，source 同步 `last_error`。

### 5.4 调度

`main.py` lifespan 增加一个轻量 `IntervalScheduler`（interval=`INVESTMENT_POLL_INTERVAL_SECONDS`）：每 tick 扫描 `enabled AND (next_poll_at IS NULL OR next_poll_at <= now)` 的 source，对每个插入一个 `pending` `TaskJob`（若同 source 无 running/pending 重复 job），单 source 失败隔离。

### 5.5 测试

`test_investment_fetch_service.py`：
- 给定 source + fake fetcher，poll 后创建 `Document` + `InvestmentItem`。
- 重复抓取不重复创建（dedupe_key 幂等）。
- 失败时 `TaskJob.status="failed"`，`source.last_error` 有值。
- 成功时 `TaskJob.output["items_created"]` 正确。

## 6. 后端 — Classifier / Claim Verifier / YouTube 集成

### 6.1 `classifier.py`

- 复用 `StructuredOutputClient` + `InvestmentClassificationSchema`（文档 §15 JSON schema 转 Pydantic）。
- 系统规则同文档 §15（不得补事实；观点层不当事实；不给买卖建议）。
- 仅写 `suggested_*` 字段与 `classification_reason`，保持 `action_status="pending_review"`，**不覆盖用户已确认字段**。
- 注册 `job_type="investment_classify"` handler（或 service 内同步调用，二选一；默认同步 service 方法 `classify_item(item_id)`，并暴露 `enqueue_classify` 给抓取后调用）。

### 6.2 `claim_verifier.py`

- 先查本地 `Document`/`InvestmentItem`（按 watchlist/thesis）。
- `tavily` 可用 → 再做 web search（复用 `WebSearchClient`）。
- 不可用 → 结论标 `verification_status="local_only"`。
- 写 `evidence_doc_ids`、`verification_summary`。

### 6.3 YouTube 集成（`backend/app/services/youtube/orchestrator.py`）

成功 persist `Document` 后调用：

```python
investment_service.create_item_from_document(
    document=document,
    info_layer="opinion",
    source_name=video.channel_name or "YouTube",
    source_url=f"https://www.youtube.com/watch?v={video.video_id}",
)
```

约束：捕获异常仅记 warning，不影响原 YouTube 总结成功；dedupe_key 防重复。

### 6.4 测试

- `test_investment_classifier.py`：观点层不被分类成 official；不输出买卖建议。
- `test_investment_claim_verifier.py`：结果带 `evidence_doc_ids`；无 Tavily → `local_only`。
- `test_youtube_orchestrator.py`（扩展）：总结成功后生成 `info_layer="opinion"` item；重复不重建；investment 失败不影响总结。

## 7. 前端

### 7.1 `frontend/src/services/investmentApi.ts`

对象字面量风格 `export const investmentApi = {...}`，inline `export type`/`interface`（文档 §4 类型），`workspaceId = "ws_default"` 默认，基于现有 `services/client.ts` 的 `apiRequest`。函数同文档 §4。新增 `getFetchJob(id)` 用于轮询。

### 7.2 页面（`frontend/src/pages/`）

`InvestmentDashboardPage` / `InvestmentWatchlistPage` / `InvestmentItemsPage` / `InvestmentClaimsPage` / `InvestmentThesesPage` / `InvestmentSourcesPage` / `InvestmentCalendarPage`（第二阶段 stub）/ `InvestmentDigestPage`（第二阶段 stub）。

数据获取：`useEffect` + `useState` + `useCallback`（无 TanStack Query，对齐仓库）。Loading→`Skeleton`/`Spin`，error→`Alert`，empty→`Empty`。`SourcesPage` 用 `setInterval` 轮询 `getFetchJob` 直到 `succeeded/failed`。

引入 AntD `Table` + `Drawer`（仓库现无先例，按 AntD v5 标准用法）。

### 7.3 组件（`frontend/src/components/investment/`）

`InfoLayerTag` / `ImpactTag` / `ReviewStatusTag` / `InvestmentItemDrawer` / `WatchlistSelector`。

### 7.4 `frontend/src/App.tsx`

加 `FundProjectionScreenOutlined` 导入；nav 加 `{ key: "/investment", ... 投资工作台 }`；加 8 条 `<Route>`。

### 7.5 测试（Vitest + RTL）

`InvestmentDashboardPage.test.tsx` / `InvestmentItemsPage.test.tsx` / `InvestmentSourcesPage.test.tsx`：空状态真实提示；API 错误显示错误；筛选层级调用正确参数；点"立即抓取"调用 `pollSource`。

## 8. 提交计划（单分支，10 次逻辑提交）

1. models + 迁移 + models 测试
2. schemas + API 骨架 + API 测试
3. P0 fetchers + httpx/feedparser 依赖 + fetcher 测试
4. 抓取 service（handler + repository）+ service 测试
5. YouTube → opinion 集成 + 测试
6. 前端第一阶段（dashboard/watchlist/items/claims/theses + tags/drawer）
7. 前端 SourcesPage + `/sources/{id}/poll` + `GET /jobs/{id}` 轮询端点
8. BLS/FRED/HKEX/CNINFO fetcher + 测试
9. classifier + claim verifier + 测试
10. 最终验证（alembic upgrade head / pytest / ruff / mypy；npm lint/test/build）

## 9. 禁止事项（文档 §17）

1. 禁止生产代码返回 mock investment items。
2. 禁止无数据源配置时自动生成示例数据。
3. 禁止把自动分类结果直接当用户确认结果。
4. 禁止把 SEC 请求的 User-Agent 留空。
5. 禁止在 fetcher 里直接操作前端展示字段，必须经 normalizer/service。

## 10. 偏离文档之处（汇总）

1. **`investment_fetch_job` 并入 `TaskJob`**（独立表 → 复用现有 worker，理由见 §1.2）。
2. **ORM 模型集中放 `infrastructure/models.py`**（而非子包内 `models.py`），保持仓库一致性。
3. **新增 `GET /investment/jobs/{id}`** 端点（文档未列，异步轮询所需）。
4. **不引入独立 APScheduler**，复用 `IntervalScheduler`（stdlib 线程），对齐 YouTube/task_worker 模式。
