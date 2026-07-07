# GLM-5.2 Agent 开发计划

日期：2026-07-02

> 给 Agent 的执行要求：按任务顺序开发。每个任务完成后运行指定测试。不要使用 mock 数据源实现产品逻辑。测试可以注入 fake HTTP response，但生产 service 必须连接真实 source 配置。

## 任务 0：读取上下文

必须先阅读：

```text
README.md
backend/README.md
backend/app/infrastructure/models.py
backend/app/api/v1/router.py
backend/app/core/config.py
backend/app/services/youtube/orchestrator.py
backend/app/services/web_search.py
frontend/src/App.tsx
outputs/investment-system-docs/01-real-data-sources.md
outputs/investment-system-docs/02-data-flow-architecture.md
outputs/investment-system-docs/03-frontend-transformation.md
outputs/investment-system-docs/04-technical-implementation.md
```

验收：

```text
Agent 能说清楚 Document 与 investment_item 的职责差异。
Agent 能说清楚为什么生产环境不能 mock 数据。
```

## 任务 1：数据库模型与迁移

修改：

```text
backend/app/infrastructure/models.py
```

新增迁移：

```text
backend/alembic/versions/202607020001_investment_information_system.py
```

新增测试：

```text
backend/tests/test_investment_models.py
```

步骤：

1. 写模型测试，验证能创建 watchlist、source、item、claim、thesis。
2. 添加 SQLAlchemy 模型。
3. 添加 Alembic migration。
4. 运行：

```bash
cd backend
alembic upgrade head
pytest tests/test_investment_models.py -v
```

验收：

```text
所有 investment 表创建成功。
investment_item.dedupe_key 在 workspace 内唯一。
source.next_poll_at 可为空。
```

## 任务 2：Schema 与 API 骨架

新增：

```text
backend/app/schemas/investment.py
backend/app/api/v1/investment.py
backend/tests/test_investment_api.py
```

修改：

```text
backend/app/api/v1/router.py
```

步骤：

1. 先写 API 测试，覆盖 list/create/update。
2. 新增 Pydantic schema。
3. 新增 APIRouter。
4. 注册 router。
5. 运行：

```bash
cd backend
pytest tests/test_investment_api.py -v
```

验收：

```text
POST /investment/watchlist 可创建观察对象。
POST /investment/items 可手动添加投资信息。
GET /investment/dashboard 返回真实数据库统计，不返回示例数据。
```

## 任务 3：真实 Fetcher 基础设施

新增：

```text
backend/app/services/investment/fetchers.py
backend/app/services/investment/normalizers.py
backend/tests/test_investment_fetchers_rss.py
backend/tests/test_investment_fetchers_sec.py
```

修改：

```text
backend/pyproject.toml
backend/app/core/config.py
```

步骤：

1. 添加 `httpx`、`feedparser` 生产依赖。
2. 添加配置项。
3. 实现 `InvestmentRawItem`。
4. 实现 `RssFetcher`。
5. 实现 `FederalReserveRssFetcher`，本质复用 RSS fetcher。
6. 实现 `SecEdgarFetcher`。
7. 测试中使用本地 fixture 响应，不访问真实网络。
8. 运行：

```bash
cd backend
pytest tests/test_investment_fetchers_rss.py -v
pytest tests/test_investment_fetchers_sec.py -v
```

验收：

```text
RSS entry 被解析为 InvestmentRawItem。
SEC filing 被解析为 InvestmentRawItem。
SEC fetcher 在 SEC_USER_AGENT 缺失时抛 SourceConfigError。
```

## 任务 4：InvestmentService 抓取入库

新增：

```text
backend/app/services/investment/repositories.py
backend/app/services/investment/service.py
backend/tests/test_investment_fetch_service.py
```

步骤：

1. 写测试：给定 source 和 fake fetcher，poll 后创建 Document + InvestmentItem。
2. 实现 repository。
3. 实现 dedupe。
4. 实现 Document upsert。
5. 实现 InvestmentItem upsert。
6. 实现 fetch job 状态记录。
7. 运行：

```bash
cd backend
pytest tests/test_investment_fetch_service.py -v
```

验收：

```text
重复抓取不重复创建 item。
失败时 fetch_job.status=failed，source.last_error 有值。
成功时 fetch_job.items_created 正确。
```

## 任务 5：YouTube 观点层集成

修改：

```text
backend/app/services/youtube/orchestrator.py
backend/tests/test_youtube_orchestrator.py
```

步骤：

1. 写测试：YouTube 总结成功后创建 opinion investment_item。
2. 在 orchestrator 成功保存 Document 后调用 InvestmentService。
3. 捕获 investment 创建失败，仅写 warning。
4. 运行：

```bash
cd backend
pytest tests/test_youtube_orchestrator.py -v
```

验收：

```text
YouTube document 对应一个 info_layer=opinion 的 investment_item。
重复总结同一视频不重复创建。
investment 创建失败不影响原 YouTube 总结成功。
```

## 任务 6：前端投资工作台第一阶段

新增：

```text
frontend/src/services/investmentApi.ts
frontend/src/pages/InvestmentDashboardPage.tsx
frontend/src/pages/InvestmentWatchlistPage.tsx
frontend/src/pages/InvestmentItemsPage.tsx
frontend/src/pages/InvestmentClaimsPage.tsx
frontend/src/pages/InvestmentThesesPage.tsx
frontend/src/components/investment/InfoLayerTag.tsx
frontend/src/components/investment/ImpactTag.tsx
frontend/src/components/investment/ReviewStatusTag.tsx
frontend/src/components/investment/InvestmentItemDrawer.tsx
frontend/src/components/investment/WatchlistSelector.tsx
```

修改：

```text
frontend/src/App.tsx
```

步骤：

1. 新增 API service 类型和函数。
2. 新增 App 路由和菜单。
3. 实现 dashboard。
4. 实现 items 列表和 drawer。
5. 实现 watchlist、claims、theses 基础 CRUD 页面。
6. 运行：

```bash
cd frontend
npm run lint
npm run test
npm run build
```

验收：

```text
左侧菜单显示投资工作台。
dashboard 不使用本地假数组。
API 错误时显示真实错误提示。
```

## 任务 7：第二阶段数据源页面与手动抓取

新增：

```text
frontend/src/pages/InvestmentSourcesPage.tsx
```

修改：

```text
frontend/src/services/investmentApi.ts
frontend/src/App.tsx
backend/app/api/v1/investment.py
```

步骤：

1. 后端增加 `POST /investment/sources/{id}/poll`。
2. 前端 source list 显示 last_error。
3. 新增 source create/edit form。
4. 支持类型：rss、sec_edgar、federal_reserve_rss。
5. 点击立即抓取后刷新列表。

验收：

```text
用户可以创建真实 RSS source。
用户可以创建 SEC source，必须填写 CIK。
用户可以点击立即抓取，后端创建 fetch_job。
```

## 任务 8：BLS/FRED/HKEX/CNINFO 扩展

新增或修改：

```text
backend/app/services/investment/fetchers.py
backend/tests/test_investment_fetchers_macro.py
backend/tests/test_investment_fetchers_hk_cn.py
```

步骤：

1. 实现 BlsFetcher。
2. 实现 FredFetcher。
3. 实现 HkexFetcher，先支持用户保存的官方搜索 URL。
4. 实现 CninfoFetcher，先支持手动 URL/PDF 和授权 API 配置。
5. 前端 source form 增加对应类型。

验收：

```text
FRED_API_KEY 未配置时 FredFetcher 抛 SourceConfigError。
BLS 无 key 时仍尝试公开 API。
HKEX/CNINFO 解析失败时落 job error，不生成假 item。
```

## 任务 9：GLM-5.2 分类与观点验证

新增：

```text
backend/app/services/investment/classifier.py
backend/app/services/investment/claim_verifier.py
backend/tests/test_investment_classifier.py
backend/tests/test_investment_claim_verifier.py
```

步骤：

1. 定义 structured output schema。
2. 使用现有 `StructuredOutputClient`。
3. 分类写入 suggested 字段，不覆盖用户确认字段。
4. 验证 claim 时先查本地 Document/InvestmentItem。
5. Tavily 可用时再做 Web Search。
6. Tavily 不可用时返回 `local_only` 结论。

验收：

```text
观点层内容不会被分类成 official。
分类不输出买卖建议。
claim 验证结果带 evidence_doc_ids。
```

## 任务 10：最终验证

运行：

```bash
cd backend
alembic upgrade head
pytest
ruff check .
mypy app

cd ../frontend
npm run lint
npm run test
npm run build
```

手动验证：

```text
1. 创建 SEC source: Apple CIK 0000320193。
2. 配置 SEC_USER_AGENT。
3. 点击立即抓取。
4. 确认投资信息列表出现真实 SEC filing。
5. 创建 Federal Reserve RSS source。
6. 点击立即抓取。
7. 确认宏观/政策信息出现真实美联储条目。
8. 添加 YouTube 视频总结。
9. 确认生成 opinion investment_item。
```

完成标准：

```text
第一阶段和第二阶段的核心链路均可用。
系统无 mock 数据。
所有新增内容可以追溯真实 source_url。
```

