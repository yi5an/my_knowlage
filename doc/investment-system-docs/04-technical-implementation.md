# 技术实现文档

日期：2026-07-02  
后端技术栈：FastAPI、SQLAlchemy 2、Alembic、Pydantic 2、APScheduler 风格定时任务  
前端技术栈：React、Vite、Ant Design

## 1. 后端新增文件

```text
backend/app/api/v1/investment.py
backend/app/schemas/investment.py
backend/app/services/investment/__init__.py
backend/app/services/investment/models.py
backend/app/services/investment/repositories.py
backend/app/services/investment/service.py
backend/app/services/investment/fetchers.py
backend/app/services/investment/normalizers.py
backend/app/services/investment/scheduler.py
backend/app/services/investment/classifier.py
backend/app/services/investment/claim_verifier.py
backend/tests/test_investment_models.py
backend/tests/test_investment_api.py
backend/tests/test_investment_fetchers_sec.py
backend/tests/test_investment_fetchers_rss.py
backend/tests/test_investment_fetch_service.py
```

## 2. 修改现有文件

```text
backend/app/infrastructure/models.py
backend/app/api/v1/router.py
backend/app/core/config.py
backend/pyproject.toml
backend/app/services/youtube/orchestrator.py
frontend/src/App.tsx
```

## 3. 依赖调整

`backend/pyproject.toml` 生产依赖增加：

```toml
"httpx>=0.27,<1.0",
"feedparser>=6.0,<7.0",
```

原因：

- `httpx` 用于真实 HTTP 数据源。
- `feedparser` 用于 RSS/Atom 解析。

不能使用 requests，因为项目已有 httpx dev 依赖，统一到 httpx 更容易测试。

## 4. 配置项

在 `backend/app/core/config.py` 新增：

```python
investment_scheduler_enabled: bool = Field(default=True, alias="INVESTMENT_SCHEDULER_ENABLED")
investment_poll_interval_seconds: int = Field(default=60, alias="INVESTMENT_POLL_INTERVAL_SECONDS")
investment_http_timeout_seconds: int = Field(default=30, alias="INVESTMENT_HTTP_TIMEOUT_SECONDS")
sec_user_agent: str | None = Field(default=None, alias="SEC_USER_AGENT")
sec_max_requests_per_second: int = Field(default=5, alias="SEC_MAX_REQUESTS_PER_SECOND")
fred_api_key: str | None = Field(default=None, alias="FRED_API_KEY")
fred_base_url: str = Field(default="https://api.stlouisfed.org/fred", alias="FRED_BASE_URL")
bls_api_key: str | None = Field(default=None, alias="BLS_API_KEY")
bls_base_url: str = Field(default="https://api.bls.gov/publicAPI/v2", alias="BLS_BASE_URL")
```

## 5. 数据库模型

在 `backend/app/infrastructure/models.py` 增加：

```text
InvestmentWatchlist
InvestmentSource
InvestmentFetchJob
InvestmentItem
InvestmentThesis
InvestmentClaim
MacroEvent
```

枚举用 `String` 存储，不使用数据库 enum，保持 SQLite/Postgres 兼容。

建议索引：

```text
idx_investment_item_workspace_layer_status
idx_investment_item_dedupe
idx_investment_item_published
idx_investment_source_due
idx_investment_claim_status
idx_investment_thesis_watchlist
```

## 6. Alembic 迁移

新增迁移：

```text
backend/alembic/versions/202607020001_investment_information_system.py
```

要求：

1. 创建全部 investment 表。
2. 添加必要索引。
3. 不修改现有 Document 表结构，除非必须。
4. downgrade 完整删除新增表和索引。

## 7. Pydantic Schema

文件：

```text
backend/app/schemas/investment.py
```

必须包含：

```text
InvestmentWatchlistCreate
InvestmentWatchlistUpdate
InvestmentWatchlistResponse
InvestmentSourceCreate
InvestmentSourceUpdate
InvestmentSourceResponse
InvestmentItemCreate
InvestmentItemUpdate
InvestmentItemResponse
InvestmentDashboardResponse
InvestmentClaimCreate
InvestmentClaimUpdate
InvestmentClaimResponse
InvestmentThesisCreate
InvestmentThesisUpdate
InvestmentThesisResponse
MacroEventResponse
```

字段约束：

```text
info_layer: Literal["primary_source", "macro_calendar", "news", "opinion"]
source_type: Literal["rss", "sec_edgar", "federal_reserve_rss", "bls", "fred", "hkex", "cninfo", "manual"]
impact_direction: Literal["positive", "negative", "neutral", "uncertain"]
```

## 8. Fetcher 设计

文件：

```text
backend/app/services/investment/fetchers.py
```

接口：

```python
class InvestmentFetcher(Protocol):
    def fetch(self, source: InvestmentSource) -> list[InvestmentRawItem]:
        ...
```

`InvestmentRawItem`：

```python
@dataclass(frozen=True)
class InvestmentRawItem:
    external_id: str
    title: str
    url: str
    source_name: str
    published_at: datetime | None
    summary: str | None
    raw_payload: dict[str, Any]
```

实现：

```text
RssFetcher
SecEdgarFetcher
FederalReserveRssFetcher
BlsFetcher
FredFetcher
HkexFetcher
CninfoFetcher
```

第一版必须完成：

```text
RssFetcher
SecEdgarFetcher
FederalReserveRssFetcher
```

第二阶段完整完成：

```text
BlsFetcher
FredFetcher
HkexFetcher
CninfoFetcher
```

## 9. SEC Fetcher 实现要求

输入 source.config：

```json
{
  "cik": "0000320193",
  "forms": ["10-K", "10-Q", "8-K", "4"],
  "limit": 20
}
```

流程：

```text
GET https://data.sec.gov/submissions/CIK{cik}.json
filter recent filings by forms
construct source_url from accessionNumber and primaryDocument
return InvestmentRawItem list
```

source_url 规则：

```text
https://www.sec.gov/Archives/edgar/data/{cik_without_leading_zero}/{accession_without_dashes}/{primaryDocument}
```

必须发送：

```text
User-Agent: settings.sec_user_agent
Accept-Encoding: gzip, deflate
```

如果 `SEC_USER_AGENT` 未配置：

```text
raise SourceConfigError("SEC_USER_AGENT is required for SEC EDGAR access")
```

## 10. RSS Fetcher 实现要求

输入：

```json
{
  "url": "https://www.federalreserve.gov/feeds/press_monetary.xml"
}
```

流程：

```text
httpx.get(url)
feedparser.parse(response.content)
for entry in entries:
  external_id = entry.id or entry.link
  title = entry.title
  url = entry.link
  published_at = parsed published date
  summary = entry.summary
```

## 11. Service 层

文件：

```text
backend/app/services/investment/service.py
```

核心方法：

```python
class InvestmentService:
    def create_watchlist(...)
    def list_watchlist(...)
    def create_item(...)
    def list_items(...)
    def update_item(...)
    def create_source(...)
    def list_sources(...)
    def poll_source(source_id: str) -> InvestmentFetchJob
    def create_claim(...)
    def verify_claim(...)
    def create_thesis(...)
    def dashboard(...)
```

`poll_source` 必须：

1. 创建 `InvestmentFetchJob(status="running")`。
2. 调用真实 fetcher。
3. 标准化 raw item。
4. upsert Document。
5. upsert InvestmentItem。
6. 更新 job 统计。
7. 更新 source last_polled_at / next_poll_at。

## 12. API 路由

文件：

```text
backend/app/api/v1/investment.py
```

新增 endpoints：

```text
GET    /api/v1/investment/dashboard
GET    /api/v1/investment/watchlist
POST   /api/v1/investment/watchlist
PATCH  /api/v1/investment/watchlist/{id}
GET    /api/v1/investment/items
POST   /api/v1/investment/items
PATCH  /api/v1/investment/items/{id}
GET    /api/v1/investment/sources
POST   /api/v1/investment/sources
PATCH  /api/v1/investment/sources/{id}
POST   /api/v1/investment/sources/{id}/poll
GET    /api/v1/investment/claims
POST   /api/v1/investment/claims
PATCH  /api/v1/investment/claims/{id}
POST   /api/v1/investment/claims/{id}/verify
GET    /api/v1/investment/theses
POST   /api/v1/investment/theses
PATCH  /api/v1/investment/theses/{id}
```

修改：

```text
backend/app/api/v1/router.py
```

加入：

```python
from app.api.v1 import investment
api_router.include_router(investment.router)
```

## 13. YouTube 集成

文件：

```text
backend/app/services/youtube/orchestrator.py
```

在成功创建 Document 后，调用：

```python
investment_service.create_item_from_document(
    document=document,
    info_layer="opinion",
    source_name=video.channel_name or "YouTube",
    source_url=f"https://www.youtube.com/watch?v={video.video_id}",
)
```

注意：

1. 不要让 YouTube pipeline 因 investment item 创建失败而整体失败。
2. 捕获异常并记录 warning。
3. 使用 dedupe_key 避免重复创建。

## 14. 定时任务

文件：

```text
backend/app/services/investment/scheduler.py
```

参考现有 YouTube scheduler 风格。

调度逻辑：

```text
每 INVESTMENT_POLL_INTERVAL_SECONDS:
  list enabled sources where next_poll_at <= now or null
  poll one by one
  each source isolated failure
```

## 15. GLM-5.2 分类 Prompt

输出 JSON schema：

```json
{
  "importance": "low|medium|high",
  "impact_direction": "positive|negative|neutral|uncertain",
  "impact_horizon": "short|mid|long|unknown",
  "thesis_impact": "supports|weakens|contradicts|unrelated|unknown",
  "reason": "string",
  "claims": [
    {
      "claim_text": "string",
      "required_evidence": ["string"]
    }
  ]
}
```

系统规则：

```text
你是投资研究信息分层助手。只能基于输入文本判断，不得补充未出现的事实。
观点层内容默认不能当作事实结论。
如果来源是一手公告或宏观官方数据，可信度可高；如果来源是个人观点，可信度必须较低。
不要给买入、卖出、持有建议，只判断信息影响。
```

## 16. 测试要求

后端：

```bash
cd backend
alembic upgrade head
pytest tests/test_investment_models.py -v
pytest tests/test_investment_api.py -v
pytest tests/test_investment_fetchers_sec.py -v
pytest tests/test_investment_fetchers_rss.py -v
ruff check .
mypy app
```

前端：

```bash
cd frontend
npm run lint
npm run test
npm run build
```

## 17. 禁止事项

1. 禁止生产代码返回 mock investment items。
2. 禁止无数据源配置时自动生成示例数据。
3. 禁止把自动分类结果直接当用户确认结果。
4. 禁止把 SEC 请求的 User-Agent 留空。
5. 禁止在 fetcher 里直接操作前端展示字段，必须经过 normalizer/service。

