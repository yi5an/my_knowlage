# 投资信息系统数据流架构

日期：2026-07-02

## 1. 总体数据流

```text
数据源配置
  -> 抓取任务 investment_fetch_job
  -> fetcher 拉取真实数据
  -> normalizer 标准化为 InvestmentRawItem
  -> deduper 去重
  -> Document 入库
  -> investment_item 入库
  -> entity/linker 关联观察对象
  -> summary/classifier 生成摘要和建议字段
  -> thesis/claim 关联假设和待验证观点
  -> frontend 投资工作台展示
```

## 2. 核心对象

### 2.1 investment_source

保存一个真实数据源配置。

```text
id
workspace_id
source_type
name
url
config
default_info_layer
default_watchlist_ids
poll_interval_seconds
last_polled_at
next_poll_at
last_error
enabled
```

### 2.2 investment_fetch_job

记录每次抓取。

```text
id
workspace_id
source_id
status
started_at
finished_at
items_seen
items_created
items_skipped
last_error
raw_error
```

### 2.3 investment_item

投资信息条目，是前端信息流的主表。

```text
id
workspace_id
document_id
source_id
dedupe_key
title
source_url
source_name
info_layer
source_credibility
published_at
event_at
summary
importance
impact_direction
impact_horizon
thesis_impact
action_status
review_at
raw_payload
created_at
updated_at
```

### 2.4 investment_watchlist

观察对象。

```text
id
workspace_id
entity_id
name
watch_type
ticker
exchange
keywords
importance
notes
enabled
```

### 2.5 investment_thesis

投资假设。

```text
id
workspace_id
watchlist_id
title
body
status
confidence
last_reviewed_at
created_at
updated_at
```

### 2.6 investment_claim

待验证观点。

```text
id
workspace_id
source_item_id
watchlist_id
thesis_id
claim_text
required_evidence
verification_status
verification_summary
evidence_doc_ids
created_at
updated_at
```

## 3. 入库边界

### 3.1 Document 负责什么

`Document` 保存原文级内容：

- title
- source_type
- source_uri
- summary / ai_summary
- metadata
- index_status
- entity_status
- relation_status

### 3.2 investment_item 负责什么

`investment_item` 保存投资语义：

- 信息层级
- 来源可信度
- 影响方向
- 影响周期
- 是否影响假设
- 处理状态
- 复查日期

原则：不要把所有投资字段塞进 `Document.metadata`。`Document.metadata` 只存源站原始字段和解析辅助字段。

## 4. 去重策略

### 4.1 通用去重

```text
dedupe_key = sha256(source_type + stable_external_id + source_url)
```

`stable_external_id` 的来源：

- SEC：accessionNumber
- RSS：guid，否则 link
- Federal Reserve RSS：guid/link
- BLS/FRED：series_id + observation_date + value
- HKEX/CNINFO：announcement_id，否则 PDF URL

### 4.2 幂等要求

1. 同一 dedupe_key 重复抓取时，不创建新 `investment_item`。
2. 如果源数据标题或摘要更新，只更新 `raw_payload` 和 `updated_at`。
3. 如果用户已经手动修改了影响判断字段，不得被自动分类覆盖。

## 5. 抓取任务流

```text
InvestmentScheduler.tick()
  -> InvestmentSourceRepository.list_due_sources()
  -> InvestmentFetchService.create_job()
  -> fetcher.fetch(source)
  -> normalizer.normalize(raw)
  -> upsert_document_and_item()
  -> link_watchlists()
  -> enqueue_classification_job()
  -> mark_job_completed()
```

失败时：

```text
catch Exception
  -> job.status = failed
  -> job.last_error = safe error message
  -> source.last_error = same
  -> source.next_poll_at = now + backoff
```

## 6. 分类与摘要流

自动分类必须使用真实 item 内容：

```text
investment_item
  -> load document content / summary / raw payload
  -> GLM-5.2 structured output
  -> write suggested fields
  -> keep action_status = pending_review
```

建议字段：

```text
suggested_importance
suggested_impact_direction
suggested_impact_horizon
suggested_thesis_impact
classification_reason
```

用户确认后写入正式字段：

```text
importance
impact_direction
impact_horizon
thesis_impact
```

## 7. YouTube 数据流改造

现有 YouTube 总结完成后，增加一步：

```text
VideoSummaryOrchestrator.summarize_url()
  -> Document(source_type="youtube")
  -> InvestmentItem(
       info_layer="opinion",
       source_name=channel_name,
       source_url=youtube_url,
       document_id=document.id,
       action_status="pending_review"
     )
```

用户可从视频总结页点击：

```text
标记为待验证观点
  -> create investment_claim
  -> claim.source_item_id = investment_item.id
```

## 8. 观点验证数据流

```text
investment_claim
  -> local RAG search
  -> investment_item search by watchlist/thesis
  -> optional Tavily web search
  -> GLM-5.2 cross-check
  -> update verification_status
  -> write evidence_doc_ids
```

生产要求：

1. 如果 Tavily key 未配置，只做本地证据验证。
2. 不能用 mock web search 生成证据。
3. 结论必须包含引用来源。

## 9. 前端展示流

```text
/investment
  -> GET /api/v1/investment/dashboard
  -> 今日待处理
  -> 待验证观点
  -> 假设被挑战
  -> 最近一手信息
  -> 最近宏观事件

/investment/items
  -> GET /api/v1/investment/items?layer=&status=&watchlist_id=

/investment/sources
  -> GET/POST/PATCH /api/v1/investment/sources
  -> POST /api/v1/investment/sources/{id}/poll
```

## 10. 时区与时间

后端统一存 UTC。

前端显示本地时间。

字段约定：

```text
published_at: 源站发布时间
event_at: 事件实际发生时间或数据观察期
retrieved_at: 系统抓取时间
created_at: 入库时间
```

