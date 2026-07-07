# 真实数据源接入说明

日期：2026-07-02  
目标：第二阶段自动采集必须接入真实数据源，不做 mock 数据源。

## 1. 数据源分级

### P0：必须实现

| 数据源 | 类型 | 用途 | 接入方式 | 是否需要 key |
|---|---|---|---|---|
| SEC EDGAR submissions | 一手信息 | 美股公司公告、10-K、10-Q、8-K、Form 4 | JSON API | 否 |
| SEC company tickers | 基础数据 | ticker -> CIK 映射 | JSON 文件 | 否 |
| Federal Reserve RSS | 宏观/政策 | FOMC 声明、会议纪要、政策新闻 | RSS | 否 |
| 通用 RSS | 新闻/官方发布 | 公司 IR、交易所、央行、媒体 RSS | RSS/Atom | 否 |
| YouTube Data API | 观点解读 | 现有 YouTube 总结和订阅 | 已存在 | 需要 YouTube API key |

### P1：建议实现

| 数据源 | 类型 | 用途 | 接入方式 | 是否需要 key |
|---|---|---|---|---|
| BLS Public Data API | 宏观数据 | CPI、PPI、就业等时间序列 | JSON API | 否，注册 key 可提高限额 |
| FRED API | 宏观数据 | 利率、收益率、就业、通胀、信用 | JSON API | 是 |
| HKEXnews | 一手信息 | 港股公告 | 官方搜索页/RSS/邮件提醒辅助 | 否 |
| 巨潮资讯 / 深证信数据服务 | 一手信息 | A 股公告 | 官方页面或授权 API | 视接口而定 |

### P2：后续再做

| 数据源 | 类型 | 说明 |
|---|---|---|
| GDELT DOC API | 全球新闻流 | 免费公开，但要严格限流，适合低频补充新闻。 |
| 付费数据商 | 新闻/公告/行情 | 如 Finnhub、Polygon、财联社、华尔街见闻等，后续通过 Provider 接口扩展。 |

## 2. SEC EDGAR

### 2.1 官方能力

SEC 官方提供 `data.sec.gov` JSON API，可访问公司提交历史和 XBRL 财务数据。官方说明中明确该 API 不需要认证或 API key，并且 JSON 会在提交传播后持续更新。

核心接口：

```text
https://www.sec.gov/files/company_tickers_exchange.json
https://data.sec.gov/submissions/CIK##########.json
https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
```

示例：

```bash
curl -H "User-Agent: KnowPilot/0.1 your-email@example.com" \
  https://data.sec.gov/submissions/CIK0000320193.json
```

### 2.2 限流与请求头

SEC 要求自动访问声明 User-Agent，并遵守公平访问规则。实现要求：

```text
SEC_USER_AGENT=KnowPilot/0.1 your-email@example.com
SEC_MAX_REQUESTS_PER_SECOND=5
```

虽然 SEC 当前公平访问上限为 10 requests/second，项目内部默认设为 5 requests/second，留出安全余量。

### 2.3 入库规则

每条 filing 映射为 `investment_item`：

```text
info_layer = primary_source
source_name = SEC EDGAR
source_url = filing document URL
source_credibility = official
published_at = filingDate + acceptanceDateTime
event_at = reportDate 或 filingDate
```

只采集以下 forms：

```text
10-K, 10-Q, 8-K, 20-F, 6-K, DEF 14A, 4, SC 13G, SC 13D
```

第一版只拉 metadata，不强制下载全文。用户点击详情或后台摘要任务需要全文时，再下载 primary document。

## 3. Federal Reserve RSS

### 3.1 真实 RSS 地址

优先接入：

```text
https://www.federalreserve.gov/feeds/press_all.xml
https://www.federalreserve.gov/feeds/press_monetary.xml
```

可选接入：

```text
https://www.federalreserve.gov/feeds/h15_data.htm
```

`h15_data.htm` 是 H.15 数据 RSS 索引页，不是单一 RSS feed。实现时先把它作为源目录，不要当作 feed 直接解析。

### 3.2 入库规则

FOMC、利率、政策声明类：

```text
info_layer = macro_calendar
source_name = Federal Reserve
source_credibility = official
impact_horizon = short_mid
```

如果标题包含 `FOMC statement`、`Minutes of the Federal Open Market Committee`，默认重要性为 `high`。

## 4. BLS Public Data API

### 4.1 核心接口

BLS Public Data API 可返回 JSON。实现优先支持单 series 和多 series。

单 series：

```text
https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}
```

常用 series：

```text
CUSR0000SA0      CPI-U: All items, U.S. city average, seasonally adjusted
CES0000000001    Total nonfarm employment
LNS14000000      Unemployment rate
```

### 4.2 配置

```text
BLS_API_KEY=
BLS_BASE_URL=https://api.bls.gov/publicAPI/v2
BLS_TIMEOUT_SECONDS=30
```

BLS key 为空时仍允许请求公开接口。若配置 key，则 POST 请求带 `registrationkey`。

### 4.3 注意事项

1. BLS 官方说明注册不是公开使用的硬性前提，但注册用户有更高能力和限制。
2. BLS 数据可能有发布后延迟，系统必须显示 `retrieved_at`。
3. 宏观数据入库为 `macro_event` 和 `investment_item`，不要只存成普通文档。

## 5. FRED API

### 5.1 核心接口

FRED API 需要 API key。

```text
https://api.stlouisfed.org/fred/series/observations
```

示例：

```bash
curl "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=$FRED_API_KEY&file_type=json&sort_order=desc&limit=5"
```

常用 series：

```text
DGS10       10-Year Treasury Constant Maturity Rate
DGS2        2-Year Treasury Constant Maturity Rate
FEDFUNDS    Effective Federal Funds Rate
UNRATE      Unemployment Rate
CPIAUCSL    CPI
PAYEMS      All Employees, Total Nonfarm
```

### 5.2 配置

```text
FRED_API_KEY=
FRED_BASE_URL=https://api.stlouisfed.org/fred
```

没有 `FRED_API_KEY` 时，FRED fetcher 必须返回配置错误并落库，不得生成假数据。

## 6. HKEXnews

### 6.1 官方页面

港股公告官方入口：

```text
https://www.hkexnews.hk/index.htm
https://www1.hkexnews.hk/search/titlesearch.xhtml
```

HKEX 页面支持按股票代码、标题、日期搜索公告。第一版实现策略：

1. 信息源管理中允许用户保存 HKEX 搜索 URL。
2. 后台按该 URL 抓取结果页面。
3. 解析公告标题、发布时间、股票代码、PDF 链接。
4. 保存原始 HTML 解析摘要和官方链接。

### 6.2 风险

HKEX 搜索页可能依赖页面参数和前端行为。实现时必须封装在 `HkexAnnouncementFetcher`，不能把页面解析散落到业务 service。

## 7. 巨潮资讯 / 深证信数据服务

### 7.1 官方入口

```text
https://www.cninfo.com.cn/
https://webapi.cninfo.com.cn/
```

第一版策略：

1. 支持用户保存巨潮公告搜索 URL。
2. 支持手动添加巨潮公告 PDF 链接。
3. 若用户拥有深证信数据服务 API 授权，再配置 API provider。

### 7.2 不允许

不允许把第三方博客里的逆向参数、加密参数、非公开接口当作项目长期依赖写入核心逻辑。

## 8. 通用 RSS

### 8.1 用途

接入公司 IR、央行、交易所、媒体、研究机构 RSS。

### 8.2 配置字段

```text
source_type = rss
url = RSS/Atom URL
default_info_layer = news | primary_source | macro_calendar | opinion
default_watchlist_ids = [...]
poll_interval_seconds = 3600
```

### 8.3 解析要求

每个 entry 至少提取：

```text
title
link
guid
published_at
summary
author
categories
raw_payload
```

去重键：

```text
sha256(source_type + guid_or_link + published_at)
```

## 9. 生产禁用 mock 数据

实现必须满足：

1. `investment` 生产 service 不允许依赖 `MockWebSearchClient`。
2. 无 key 时返回 `source_config_error`，并写入 `investment_fetch_job.last_error`。
3. 前端显示“数据源未配置”，而不是显示假数据。
4. tests 可以注入 fake HTTP client，但 fake client 只存在于测试文件。

## 10. 参考来源

- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC Accessing EDGAR Data: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- BLS Public Data API: https://www.bls.gov/bls/api_features.htm
- FRED API: https://fred.stlouisfed.org/docs/api/fred/
- FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
- Federal Reserve RSS: https://www.federalreserve.gov/feeds/feeds.htm
- HKEXnews: https://www.hkexnews.hk/index.htm
- HKEX title search: https://www1.hkexnews.hk/search/titlesearch.xhtml
- CNINFO: https://www.cninfo.com.cn/
- 深证信数据服务: https://webapi.cninfo.com.cn/

