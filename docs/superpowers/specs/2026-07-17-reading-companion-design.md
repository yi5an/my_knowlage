# AI 陪读与跨资料佐证设计

## 目标

为 KnowPilot 阅读器增加主动式 AI 陪读能力。用户打开一篇已入库文档时，系统应在正文中标记值得关注的内容，并在右侧面板解释三件事：

1. 这段内容说了什么，哪些概念或数据值得理解；
2. 它对已关注的行业主题或宏观变量可能意味着什么；
3. 平台内其他已持久化资料是支持、冲突，还是不足以佐证该判断。

该能力服务研究与学习，不提供买入、卖出、持有建议，也不会自动修改投资假设、信号或人工确认字段。

## 范围与边界

首期仅分析一个文档的最新版本，并只在同一 workspace 内检索佐证。可作为佐证的已持久化内容包括：

- 文档及其 chunk、研究报告、摘录和标注；
- YouTube 字幕、摘要、视觉 OCR 与结构化画面笔记；
- 投资信息条目、抽取事实、早期信号、待验证观点和宏观日历事件。

当前平台没有可检索的持久化对话消息表，因此不会把临时聊天内容伪装成证据。后续若增加消息归档，只需实现统一的证据检索适配器即可加入同一流程。

首期不联网搜索、不生成外部事实、不自动创建投资结论；联网深度研究仍由现有研究工作流负责。

## 用户体验

阅读页由现有静态原型改为面向具体文档的页面，路由为 `/reader/:documentId`。页面保留大纲、正文和右侧助手面板三栏：

- 正文只显示有明确原文定位的轻量标记。理解、影响和风险分别使用不同但低干扰的颜色；
- 右侧按“优先阅读”展示陪读卡。卡片包含结论、为什么标记、置信度、关联主题/宏观变量，以及可展开的原文证据；
- 用户点击正文标记或卡片时，正文滚动到对应 chunk 与字符范围，并显示当前段落和外部佐证；
- 用户可以确认、忽略、添加笔记或把卡片转为研究问题。首期的确认/忽略只影响卡片状态，不训练模型，也不改写源文档；
- 若分析尚未生成，页面展示任务状态。用户可手动重新分析；同一文档版本的进行中任务不重复创建。

默认排序为：有冲突证据的高风险卡、被多份独立资料支持的高影响卡、其余理解卡。没有足够本地佐证时，卡片必须明确显示“本地资料不足”，而不是把相关性视为支持。

## 核心数据模型

新增持久化分析结果，避免每次打开阅读器都重新调用模型：

### `reading_analysis`

- `id`、`workspace_id`、`document_id`、`version_id`；
- `status`：`pending`、`running`、`completed`、`failed`；
- `model_name`、`prompt_version`、`error_message`；
- `created_at`、`updated_at`、`completed_at`。

同一 `document_id + version_id` 只有一个当前分析结果。保存新版本后，旧分析保留只读历史，新版本进入待分析状态。

### `reading_insight`

- `id`、`analysis_id`、`kind`：`understanding`、`impact`、`risk`；
- `headline`、`explanation`、`why_it_matters`；
- 原文锚点：`chunk_id`、`start_offset`、`end_offset`、`evidence_text`；
- `confidence`（0–1）、`priority`（1–5）、`evidence_state`：`corroborated`、`conflicted`、`insufficient`；
- `status`：`active`、`confirmed`、`dismissed`；
- `theme_ids`、`macro_event_ids`、`entity_ids`；
- `created_at`、`updated_at`。

### `reading_corroboration`

- `id`、`insight_id`；
- 通用来源引用：`source_kind`、`source_id`、`document_id`、`chunk_id`；
- `stance`：`supports`、`contradicts`、`contextualizes`；
- `excerpt`、`source_title`、`source_published_at`、`confidence`；
- `retrieval_score`、`created_at`。

该通用引用模型使不同类型的平台内容都以相同格式展示，且始终能跳回原始资料。缺少相关记录不创建伪造的“反驳”来源；系统改以 insight 的 `evidence_state=insufficient` 表达证据不足。

## 分析与佐证流程

```text
文档最新版本 + chunks
  → 结构化陪读提取
  → 原文锚点校验
  → 为每条 insight 构造本地检索查询
  → 混合检索其他平台资料（排除当前锚点）
  → 结构化判断支持 / 冲突 / 补充 / 不足
  → 保存 insight 与 corroboration
  → 阅读器展示、用户确认或忽略
```

1. **陪读提取**：模型以 chunk 为单位输出不超过三个高价值 insight，必须给出原文片段、字符范围、类型、解释、影响对象和置信度。服务端验证范围能在目标 chunk 中精确匹配；失败的锚点不入库。
2. **本地检索**：从 insight 的原文、实体、主题和宏观变量生成查询，复用 `RagService` 的混合检索，再补充查询同 workspace 的投资事实、信号、观点和宏观事件。当前 chunk 与同一原文片段不能作为外部佐证。
3. **佐证判断**：模型只能依据返回的候选片段输出 `supports`、`contradicts` 或 `contextualizes`。每条判断必须指向候选的原始文本；无直接证据时记录不足，不输出结论。
4. **影响表达**：`impact` 卡描述“可能的行业/宏观传导路径、时间尺度和不确定性”，不描述价格目标或交易操作。`risk` 卡优先标记来源层级低、时间过期、事实与观点混淆、或跨资料冲突。

所有模型结果继续使用 Pydantic JSON Schema 与现有 `StructuredOutputClient`。分析任务写入 `task_job`，任务输入、输出摘要、失败原因与可重试状态均可查询。

## API 契约

新增 schema 后提供以下接口：

- `GET /api/v1/documents/{document_id}/reader`：返回文档最新版本、结构化大纲、chunks、现有分析状态与已完成 insight；
- `POST /api/v1/documents/{document_id}/reading-analyses`：为最新版本创建或复用异步分析任务，返回 `task_job` 与 `reading_analysis` 标识；
- `GET /api/v1/reading-analyses/{analysis_id}`：轮询状态及完整 insight/佐证结果；
- `PATCH /api/v1/reading-insights/{insight_id}`：只允许更新 `confirmed` 或 `dismissed` 状态及用户笔记；
- `POST /api/v1/reading-insights/{insight_id}/research-tasks`：以卡片内容和已选证据创建已有的深度研究任务。

所有响应中的 insight 和 corroboration 都必须包含证据文本、来源引用和置信度；失败响应使用既有统一错误格式。接口不返回其他 workspace 的内容。

## 后端边界

- `schemas/reading_companion.py`：所有 API、模型结构化输出和状态 enum；
- `services/reading_companion.py`：提取、检索编排、佐证判断、原文锚点验证；
- `services/reading_companion_prompts.py`：版本化 prompt 构造，不在 service 内硬编码长提示词；
- `workers`/`task_worker`：注册 `reading_analysis` 任务处理器；
- `infrastructure/models.py` 与 Alembic：持久化表及索引；
- `api/v1/reading_companion.py`：只处理鉴权、请求/响应和任务触发。

现有 `RagService` 保持其搜索职责。陪读服务通过稳定接口消费检索结果，投资信息检索则通过一个小型 repository/adapter 提供，避免 API 或 UI 直接查询模型表。

## 前端边界

- `services/readingCompanionApi.ts`：阅读页和分析接口类型；
- `pages/ReaderPage.tsx`：加载真实文档、处理分析状态、协调定位；
- `components/reading/DocumentOutline.tsx`、`InsightMarker.tsx`、`InsightPanel.tsx`、`CorroborationList.tsx`：每个组件只负责一个呈现层；
- `types/readingCompanion.ts`：与后端 schema 对齐的前端类型。

页面不直接调用模型，也不根据颜色推断结论；所有展示内容来自分析 API。阅读页应在窄屏退化为正文优先、侧栏抽屉，而不是隐藏证据。

## 错误处理与质量规则

- 任一模型输出未通过 Schema 或原文锚点验证时，该次任务失败并可重试，不写入半成品 insight；
- 检索失败可保留已经验证的当前文档理解卡，但必须将跨资料状态标为 `insufficient`，并在任务输出中记录失败阶段；
- 同一来源的重复片段只保留一次；不同来源即使结论相同也保留，以支持来源数量与冲突展示；
- 低于 0.60 的模型置信度不显示为正文主动标记，只在“待复核”分组中出现；
- 高优先级影响或风险卡必须至少有一个本地佐证或明确的“证据不足”标签；
- 用户的确认、忽略和笔记记录操作人、时间和原 insight，不覆盖模型原始输出。

## 测试与验收

后端测试覆盖：

- Pydantic schema 对非法状态、越界置信度和无锚点 insight 的拒绝；
- 原文锚点验证、当前 chunk 排除、同 workspace 隔离与来源去重；
- 支持、冲突、补充、证据不足四种佐证结果；
- 任务幂等、失败重试、文档版本变更后的失效与重建；
- API 的任务触发、轮询、状态更新和研究任务创建。

前端测试覆盖：

- 加载、运行中、失败、无 insight 与完成状态；
- 点击卡片定位正文，点击标记激活对应卡片；
- 支持/冲突/不足证据的文案和来源跳转；
- 确认、忽略、创建研究任务的请求行为。

验收条件：已分析文档可展示至少一类主动标记；每个标记可回到当前原文；跨资料结论可展开并访问原始平台记录；没有证据时明确提示；整个过程不生成交易建议，也不修改人工确认的投资字段。

## 分阶段交付

第一阶段交付最新文档版本的主动理解、风险标记与本地文档/研究/视频佐证，以及阅读器完整状态流。第二阶段接入投资信息、主题与宏观事件适配器，并生成影响卡与研究任务。第三阶段再评估联网佐证、用户反馈学习和跨版本变化陪读。
