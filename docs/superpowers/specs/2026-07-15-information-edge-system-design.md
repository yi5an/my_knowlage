# KnowPilot 信息差系统 — 设计规格

日期：2026-07-15
状态：待用户确认

## 1. 真实目标

KnowPilot 的目标不是做热点聚合、摘要列表或单独的雷达页面，而是建立一个面向投资研究的 **主题化信息差系统**：

> 围绕固定投资主题，持续采集一手源、人源、观点源、新闻确认和市场反馈，识别弱信号，反推传播来源，判断哪些信息比 YouTube 博主、主流媒体和市场情绪更早、更干净、更可行动。

系统必须回答六个问题：

1. 这个信息属于哪个持续跟踪主题？
2. 它最早出现在哪个源？
3. 它是否来自一手源，还是来自人源、媒体、博主观点或市场反馈？
4. 它是不是正在反复出现的弱信号？
5. 它后来是否被 YouTube 博主、新闻或市场验证？
6. 它对观察对象和投资假设意味着什么？

## 2. 核心原则

### 2.1 主题先行

信息差只会出现在持续追踪的领域里。系统必须以“主题/观察对象”为中心组织采集、分层、信号、验证和简报，不允许所有内容混在一个泛化信息池里。

初始主题范围：

- **AI 算力**：NVDA、AMD、台积电、博通、光模块、数据中心电力、AI 服务器、HBM、先进封装。
- **宏观**：美联储、通胀、就业、财政、美元流动性、利率曲线、财政部发债、全球央行。
- **特斯拉 / Robotaxi / 自动驾驶**：Tesla、Robotaxi、FSD、Waymo、自动驾驶监管、车险、出行平台。
- **黄金 / 能源 / 军工 / 消费 / 港股科技**：作为可配置主题族，不做硬编码逻辑。

后续新增主题必须配置来源，而不是只加关键词。

### 2.2 一手源优先

一手源比媒体早，也比博主干净。每个主题必须有一手源优先级配置。

一手源类型：

- 公司官网 IR、新闻稿、财报、电话会文字稿。
- SEC 文件：10-K、10-Q、8-K、Form 4、S-1、13F。
- 央行、财政部、统计局、交易所、监管机构公告。
- 供应链公司公告、订单、交付、价格、产能、库存相关公开信息。
- 法院文件、监管文件、政策文件。
- GitHub、论文、专利、招聘信息。

一手源进入系统时默认 `source_layer = primary_source`，可信度高于媒体和观点源，但仍要保留证据和置信度。

### 2.3 人源是信息差核心

YouTube 博主通常是传播出口，不是源头。系统必须为每个主题建立“观察账号池”。

人源类型：

- 公司高管、员工、前员工。
- 研究员、记者、行业从业者。
- 券商分析师、宏观交易员、产业专家。
- 小众 Substack 作者、论坛用户、Reddit/Discord 讨论节点。
- 特定领域 KOL：AI、芯片、宏观、地缘政治、自动驾驶。

人源进入系统时默认 `source_layer = human_source` 或 `expert_opinion`。同一个人的连续表达可以形成弱信号，但不能直接当作事实，需要一手源或市场反馈验证。

### 2.4 分层采集

所有入库信息必须标记来源层级：

- `primary_source`：一手源。
- `human_source`：X、Substack、论坛、专家、从业者。
- `expert_opinion`：YouTube、播客、长文观点、分析师观点。
- `news_confirmation`：Reuters、Bloomberg、WSJ、财联社等确认性报道。
- `market_feedback`：股价、期权、利率、汇率、商品、成交量、波动率。

现有 `InvestmentItem.info_layer` 可以继续承载大类，但需要扩展或新增 `source_layer`，避免“观点层”和“人源层”混淆。

### 2.5 弱信号优先于结论

信息差往往不是一句结论，而是弱信号反复出现。系统必须识别、聚类和追踪弱信号，而不是只生成摘要。

弱信号类型：

- 多家公司同时提到库存压力、订单放缓、价格压力。
- 招聘突然增加或减少。
- 高管频繁开始提某个业务、风险、市场或政策。
- 供应链订单、价格、交付周期、产能利用率变化。
- 政策文件措辞变化。
- 小圈子讨论突然升温。
- 市场反馈先于新闻确认出现异常。

弱信号状态：

- `new`：首次出现。
- `repeating`：不同源反复出现。
- `validated`：被一手源、新闻确认或市场反馈验证。
- `refuted`：被后续信息证伪。
- `stale`：超过有效窗口且未验证。
- `noise`：被判定为噪音。

### 2.6 反推来源

看 YouTube 视频时，系统必须反推它的信息来源，而不是只总结视频。

对每个 YouTube 摘要，系统要追问：

- 博主引用了什么文件？
- 引用了谁的推文或文章？
- 有没有原始链接？
- 内容是事实、传闻、还是推理？
- 这个信息是否已经被市场反映？
- 平台是否在视频发布前已经采到相同或相近事实？

来源反推输出必须区分：

- `confirmed_citation`：视频明确引用原始链接或原文。
- `likely_source`：语义、实体、时间窗口高度匹配。
- `same_topic`：相关但不能认为是来源。
- `unmatched`：未找到可能来源。

## 3. 系统对象

### 3.1 InvestmentTheme

主题是系统最高层对象。它不只是 watchlist 的别名，而是采集和判断的边界。

字段建议：

- `id`
- `workspace_id`
- `name`
- `description`
- `theme_type`：`company_cluster | macro | sector | asset | geopolitics | custom`
- `keywords`
- `entities`
- `tickers`
- `enabled`
- `priority`
- `created_at`
- `updated_at`

现有 `InvestmentWatchlist` 可以逐步迁移为主题视图，或保留 watchlist 作为用户关注对象，新增 `InvestmentTheme` 作为更强的研究主题。

### 3.2 ThemeSource

主题绑定的信息源配置。

字段建议：

- `theme_id`
- `source_id`
- `source_layer`
- `priority`
- `collector_type`
- `coverage_notes`
- `enabled`

每个主题必须至少有一个一手源或明确标记“一手源缺口”。

### 3.3 PersonSource

人源账号池。

字段建议：

- `id`
- `workspace_id`
- `theme_ids`
- `platform`：`x | substack | reddit | discord | youtube | website | other`
- `handle`
- `display_name`
- `role_type`：`executive | employee | researcher | journalist | analyst | trader | practitioner | kol | other`
- `credibility`
- `noise_level`
- `known_bias`
- `enabled`

### 3.4 InformationEvent

统一事件层，把不同来源的信息归一到“某个主题下发生了一件事”。

它可以从现有 `InvestmentItem` 派生，也可以后续物化为独立表。

关键字段：

- `theme_id`
- `item_id`
- `source_layer`
- `published_at`
- `collected_at`
- `entities`
- `event_type`
- `event_summary_zh`
- `evidence_url`
- `evidence_excerpt`
- `confidence`

### 3.5 EarlySignal

现有 `InvestmentSignal` 是基础，但需要升级为“弱信号生命周期”。

新增或扩展字段：

- `signal_stage`
- `source_layers`
- `first_source_layer`
- `first_source_id`
- `first_seen_at`
- `last_seen_at`
- `validation_state`
- `validation_sources`
- `market_feedback`
- `lead_time_hours`
- `information_edge_score`
- `actionability`

### 3.6 SourceTrace

来源反推记录，用于连接 YouTube、媒体、X、人源和一手源。

字段建议：

- `target_item_id`
- `source_item_id`
- `trace_type`
- `match_reason`
- `matched_fact`
- `lead_time_hours`
- `confidence`

现有 YouTube `source_traces` 可以作为 API 输出，后续应物化成可查询记录。

## 4. 采集分层设计

### 4.1 一手源采集

按主题配置：

- AI 算力：NVDA/AMD/TSMC/Broadcom/Marvell/Arista/Supermicro IR、SEC、财报电话会、供应链公告、专利、招聘。
- 宏观：FOMC、Fed speeches、Treasury、BLS、BEA、CPI/PCE/NFP、财政部发债、央行资产负债表。
- Tesla/Robotaxi：Tesla IR、SEC、NHTSA、加州 DMV、法院/监管文件、招聘、专利、保险/车队数据源。

采集结果进入 `primary_source`，并自动抽取事实。

### 4.2 人源采集

按主题维护账号池：

- X 账号：公司高管、记者、研究员、交易员、产业 KOL。
- Substack：主题相关作者。
- Reddit/论坛/Discord：只采特定社区或关键词，不做泛采。

采集结果进入 `human_source`，先作为弱信号候选，不直接作为已验证事实。

### 4.3 观点源采集

YouTube、播客、分析师长文进入 `expert_opinion`。

观点源用于：

- 反推它用了哪些一手源或人源。
- 判断平台是否已经提前采到相同信号。
- 衡量某个信号从小圈子到公开传播的扩散速度。

### 4.4 新闻确认

新闻源进入 `news_confirmation`。

新闻不是最早信号，但可用于验证：

- 一手源是否被媒体确认。
- 人源传闻是否被可靠媒体确认。
- 市场是否已经充分传播。

### 4.5 市场反馈

市场数据进入 `market_feedback`。

用于判断：

- 信息是否已经反映在价格里。
- 弱信号出现后，相关资产是否有异常反应。
- 信息差是否仍有行动价值。

第一阶段可以先接入轻量市场字段：标的价格变化、成交量、波动率、利率/汇率/商品价格变化。

## 5. 信息差评分

`information_edge_score` 不是单纯热度分数，而是“早、真、相关、未充分传播、可行动”的综合分。

建议公式：

```
score =
  lead_time_score * 0.25
  + source_quality_score * 0.20
  + signal_repetition_score * 0.15
  + theme_relevance_score * 0.15
  + validation_score * 0.15
  + market_unpriced_score * 0.10
```

分项解释：

- `lead_time_score`：相对 YouTube、新闻确认或市场反馈的领先时间。
- `source_quality_score`：一手源最高，人源按可信度，观点源较低。
- `signal_repetition_score`：多源独立重复更高，同源转发链要降权。
- `theme_relevance_score`：是否命中主题实体、关键词、假设。
- `validation_score`：被一手源、新闻、市场反馈验证则提高；被证伪则归零。
- `market_unpriced_score`：尚未出现明显市场反应更高，已广泛传播则降低。

输出等级：

- `A`：立即关注，进入今日信息差简报。
- `B`：加入观察，等待验证。
- `C`：弱信号，保留但不打扰。
- `D`：噪音或已过时。

## 6. 用户工作流

### 6.1 建主题

用户先建或选择主题，如“AI 算力”。

系统要求：

- 配置至少一类一手源。
- 配置人源账号池。
- 配置关键词和实体。
- 配置相关投资假设。

### 6.2 自动采集

系统按主题采集不同层级来源，并统一入库。

每条信息必须显示：

- 来源层级。
- 原始链接。
- 发布时间。
- 采集时间。
- 所属主题。
- 证据摘录。

### 6.3 弱信号池

系统自动聚类最近事实和观点，形成弱信号。

用户可以：

- 标记为跟踪。
- 标记为噪音。
- 升级为待验证事实。
- 关联投资假设。

### 6.4 YouTube 反推

打开 YouTube 总结时，页面显示：

- 视频中出现的关键事实/观点。
- 平台在视频发布前是否已采到相同信息。
- 可能的一手源、人源、新闻确认。
- 领先时间。
- 匹配证据。

### 6.5 信息差简报

每日简报不再只是新闻摘要，而是：

- 今天最高分信息差。
- 新出现弱信号。
- 被验证或证伪的旧信号。
- YouTube/媒体开始传播但平台已提前捕捉的主题。
- 对投资假设的支持、削弱、反驳。

## 7. 页面形态

页面是系统出口，不是目标本身。

需要新增或强化：

- **主题中心**：每个主题的来源、账号池、弱信号、假设、最新传播链。
- **分层信息流**：按一手源、人源、观点源、新闻确认、市场反馈过滤。
- **弱信号池**：按状态和分数查看可跟踪信号。
- **来源反推**：嵌入 YouTube 总结页和主题详情页。
- **信息差简报**：每日/每周输出可行动判断。

## 8. 后端实现原则

### 8.1 不做泛化热点抓取

所有抓取任务必须绑定主题、来源或账号池。没有主题归属的信息可以进入暂存区，但不能进入主信息差评分。

### 8.2 所有 AI 结果必须有证据和置信度

事实、信号、来源追踪、假设影响都必须有：

- `evidence_url`
- `evidence_excerpt`
- `confidence`

### 8.3 不把观点当事实

观点源和人源内容默认是候选信号。只有被一手源、新闻确认或市场反馈支持后，才能提升验证状态。

### 8.4 反推来源要表达不确定性

系统不能把语义相似直接写成“来源确定”。必须显示 `confirmed_citation / likely_source / same_topic / unmatched`。

### 8.5 评分可解释

每个信息差分数必须能展开看到分项原因，而不是只显示一个黑盒分数。

## 9. 与现有系统的关系

现有能力可复用：

- `InvestmentWatchlist`：可作为主题的用户视图或迁移基础。
- `InvestmentSource`：继续做数据源配置。
- `InvestmentItem`：继续做统一信息入库表。
- `InvestmentFact`：继续做事实抽取层。
- `InvestmentSignal`：升级为弱信号生命周期。
- `InvestmentClaim` / `InvestmentThesis`：继续做验证和假设影响。
- YouTube `source_traces`：升级为通用 SourceTrace。
- X 采集器：变成主题账号池采集执行器。
- 每日简报：升级为信息差简报。

需要补齐：

- 主题模型。
- 来源层级字段。
- 人源账号池。
- 一手源优先级配置。
- 弱信号状态和分数。
- 通用来源追踪记录。
- 市场反馈接入。

## 10. 验收标准

系统完成后，必须能用一个主题回答：

1. 这个主题当前有哪些一手源、人源、观点源、新闻确认、市场反馈？
2. 今天出现了哪些新弱信号？
3. 哪些弱信号已经重复出现？
4. 哪些信号被一手源或新闻验证？
5. 哪些 YouTube 视频讲到的信息，平台之前已经采到？
6. 平台领先了多久？
7. 这条信息影响哪个观察对象或投资假设？
8. 现在应当立即关注、继续验证、忽略，还是判定为已过时？

不能只展示信息列表；必须展示来源、分层、证据、领先时间、验证状态和行动建议。

## 11. 非目标

以下内容不属于本设计目标：

- 泛泛追全网热点。
- 用单一 LLM 总结替代来源证据。
- 把 YouTube 博主当作主要源头。
- 没有主题边界的 X 搜索。
- 没有证据链接的投资建议。
- 黑盒打分。

## 12. 实施顺序约束

实现可以分任务提交，但每个任务必须服务完整目标。

建议顺序：

1. 主题模型和主题来源绑定。
2. 一手源优先级和人源账号池。
3. 来源层级字段和分层信息流。
4. 弱信号生命周期和信息差评分。
5. 通用来源反推。
6. YouTube 反推强化。
7. 市场反馈接入。
8. 信息差简报和主题中心页面。

禁止先做一个脱离主题和来源层级的普通“雷达列表”。
