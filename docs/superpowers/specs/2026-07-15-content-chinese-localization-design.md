# 采集内容中文化设计

## 目标

让 KnowPilot 采集到的内容稳定产出中文版本，重点覆盖：

- YouTube 总结、要点、标签、脑图、视觉资料结构化说明。
- 投资信息中的标题和摘要。
- 宏观日历中的标题和摘要。
- X、官方源、RSS、手工导入等进入投资信息流的内容。

目标不是只把界面按钮变成中文，而是让用户阅读到的核心内容默认是中文，同时保留原始内容作为证据和排障依据。

## 已确认根因

### YouTube

当前 YouTube 链路存在三个导致英文输出的点：

1. 生产环境配置曾出现 `TRANSLATE_TO_CHINESE=false`，导致非中文字幕不会先翻译。
2. 总结 prompt 明确要求 `Use the same language as the transcript`，所以英文字幕会生成英文总结。
3. 字幕翻译失败时会回退原字幕继续总结，不阻断流程，因此会出现“总结成功但内容是英文”。

### 投资信息和宏观日历

投资信息已经有 `title_zh` 和 `summary_zh` 字段，页面也大多优先展示中文字段。但存量数据中仍存在中文字段为空的内容，例如宏观日历条目 `title_zh=null`、`summary_zh=null`。

原因包括：

- 翻译 job 失败后没有统一补偿机制。
- 已采集数据没有稳定的批量补翻译流程。
- Dashboard 只显示 untranslated 数量，没有自动把存量缺口处理完。

## 非目标

- 不翻译原文证据本身，例如原始字幕、推文正文、网页原文、OCR 原文。
- 不删除英文原文。
- 不修改数据库中的枚举值和 API 字段名。
- 不把 URL、模型名、API 名、股票代码、公司英文名强行翻译。
- 不改变采集源和订阅策略。

## 设计原则

1. 中文是默认阅读语言。
2. 原文必须保留，可追溯。
3. 翻译失败要可见、可重试，不能静默变成“英文内容已完成”。
4. 新增数据和存量数据都要覆盖。
5. 翻译流程要幂等，重复执行不会产生重复数据或覆盖人工修正。

## YouTube 中文化设计

### 新视频处理

YouTube 总结最终输出必须为简体中文：

- `summary_json.tldr`
- `summary_json.key_points[].point`
- `summary_json.quotes[].text`
- `summary_json.chapters[].title`
- `summary_json.tags`
- `mindmap_data`
- 视觉资料 `structured_notes`

处理方式：

1. `TRANSLATE_TO_CHINESE` 默认保持开启。
2. 字幕是非中文时，先尝试字幕逐段翻译。
3. 即使字幕翻译失败，summary prompt 也必须要求模型用简体中文输出，而不是跟随字幕语言。
4. Map step、Reduce step、Mindmap prompt 都统一要求简体中文输出。
5. Document 保留 `transcript_lang`，用于区分原始字幕语言和最终总结语言。

### 翻译失败处理

如果字幕翻译失败：

- 不阻断总结。
- 记录 warning 到视频或文档 metadata，例如 `translation_warning`。
- 总结阶段继续使用原字幕，但 prompt 强制中文输出。

如果总结产出仍明显是英文：

- 标记为需要补中文化。
- 入队一个 `youtube_summary_localize` 或复用 summary retry 的中文重生成任务。

### 存量 YouTube 补中文

增加后端脚本或任务：

- 扫描已完成 YouTube summary。
- 判断 `tldr/key_points/tags/mindmap` 是否主要为英文。
- 对英文总结重新生成中文结构化结果。
- 保留原始英文 summary 到 metadata，例如 `original_summary_json`，避免丢证据。

## 投资信息与宏观日历中文化设计

### 新增内容

所有创建 `InvestmentItem` 的入口都必须进入 post-processing：

- 手工创建。
- X 网页采集。
- X API 或未来浏览器 API 采集。
- YouTube mirror 到投资信息。
- RSS / 官方源 / 宏观源。
- 批量导入。

post-processing 至少包括：

1. 翻译 `title_zh` 和 `summary_zh`。
2. 分类。
3. 事实抽取。

翻译 job 对每个 item/source 保持幂等，不重复创建活跃 job。

### 存量补翻译

增加或完善批量补翻译能力：

- 扫描 `title_zh IS NULL` 或 `summary IS NOT NULL AND summary_zh IS NULL` 的 InvestmentItem。
- 按发布时间倒序或创建时间倒序处理，优先补最近内容。
- 每批限制数量，避免一次性消耗过多 LLM。
- 失败 job 可重新入队。

### 宏观日历

宏观日历页面继续基于 `InvestmentItem.info_layer = macro_calendar`。

展示策略：

- 优先展示 `title_zh` / `summary_zh`。
- 如果中文字段为空，显示原文的同时加“待翻译”标记。
- 提供批量补翻译入口或由后台自动补翻译。

## 视觉资料和 OCR 中文化设计

OCR 原文保留，不直接改写。

结构化视觉资料需要中文：

- `structured_notes.title`
- `structured_notes.bullets`
- 视觉脑图节点

如果 OCR 是英文：

1. OCR 原文作为证据保存。
2. LLM 结构化时输出中文摘要/节点。
3. 页面展示中文结构化内容，必要时可展开原始 OCR。

## 数据模型影响

优先复用现有字段：

- `InvestmentItem.title_zh`
- `InvestmentItem.summary_zh`
- `InvestmentFact.fact_text_zh`
- `Document.summary_json`
- `Document.mindmap_data`
- `VideoFrameAnalysis.structured_notes`

可能新增 metadata 字段，不新增主表字段：

- `translation_warning`
- `summary_language`
- `original_summary_json`
- `localized_at`

是否新增独立 job type 由实施阶段决定。优先复用现有 `investment_translation`，YouTube 存量中文重生成可新增专门 job 或脚本。

## API 和前端影响

### 后端

- YouTube summary prompt 改为强制中文输出。
- 投资翻译 job 增加存量补偿入口。
- Dashboard 的 `untranslated_count` 继续作为观察指标。
- 增加批量补翻译脚本或 API。

### 前端

- 投资信息、宏观日历、每日简报继续优先展示中文字段。
- 对缺中文字段的条目显示“待翻译”标记。
- YouTube 页面展示中文 summary；原字幕仍在“原字幕”里展示。
- 失败或待翻译状态应可见。

## 测试策略

### YouTube

- 非中文字幕输入时，summary prompt 必须要求简体中文输出。
- Map-Reduce 的 map、reduce prompt 都必须要求简体中文。
- 字幕翻译失败时，仍然生成中文 summary prompt，并记录 warning。
- 存量英文 summary 可被识别为需要补中文。

### 投资和宏观

- 创建宏观/投资 item 后会入队翻译 job。
- 存量缺 `title_zh` / `summary_zh` 的条目可被批量补翻译。
- 翻译 job 失败后可以重新入队。
- 页面优先展示中文字段，缺失时显示待翻译。

### 验证命令

```bash
cd backend
pytest backend/tests/test_translation.py backend/tests/test_youtube_orchestrator.py backend/tests/test_investment_translation.py backend/tests/test_investment_api.py
ruff check app tests

cd ../frontend
npm run test
npm run lint
npm run build
```

## 验收标准

- 新采集 YouTube 视频的总结、要点、标签、脑图默认是中文。
- 新采集投资信息和宏观日历条目会自动补 `title_zh` / `summary_zh`。
- 存量宏观日历英文条目可以批量补翻译。
- 存量英文 YouTube 总结可以识别并重新生成中文版本。
- 翻译失败不会静默消失，用户能看到待翻译或失败状态。
- 原始英文内容仍可追溯。
- 相关测试、lint、build 通过。

## 实施顺序

1. 修 YouTube summary prompt，强制最终输出中文。
2. 打开并校验生产 `TRANSLATE_TO_CHINESE=true`。
3. 增加 YouTube 翻译失败 metadata 记录。
4. 增加投资/宏观存量补翻译脚本或 API。
5. 前端给缺中文内容加“待翻译”标记。
6. 增加存量 YouTube 英文 summary 检测和补中文任务。
7. 跑测试，部署，并对远端存量执行补翻译。
