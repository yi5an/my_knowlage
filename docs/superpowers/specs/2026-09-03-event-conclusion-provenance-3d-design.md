# KnowPilot 事件—结论溯源真 3D 图设计

状态：用户已确认设计，待实现计划

日期：2026-09-03

## 1. 背景

KnowPilot 已经具备文档、分块、实体关系、投资信息、事实、信号、观点、投资逻辑、研究报告和来源追踪等能力，但现有知识图谱主要展示实体关系，无法直接回答以下问题：

1. 一条投资判断或通用研究结论由哪些事件和事实支撑？
2. 每个事件和事实最终来自原文的哪一段、PDF 哪一页、视频哪一秒或图片哪个区域？
3. 某个事件影响了哪些结论？
4. 哪些路径已确认，哪些由 AI 推断，哪些待审核或存在冲突？

本设计新增独立的“事件—结论溯源图”。它与现有实体知识图谱并列存在，共享底层文档、图存储适配器和部分图形基础设施，但不混淆两类图的语义。

## 2. 已确认的产品决策

- 使用三层空间结构：结论层、事件/事实层、证据层。
- 同时支持投资结论和通用研究结论。
- 同时支持“结论向下审计”和“事件向上看影响”。
- 证据必须精确定位到段落、字符区间、PDF 页码与区域、音视频时间段或图片区域。
- 已确认、AI 推断、待审核、被驳回和存在冲突的路径全部展示，并通过视觉编码严格区分。
- 默认视觉采用空间三层全景，而不是平面分栏图。
- 画布必须是真 3D WebGL 场景，支持环绕旋转、平移、滚轮缩放、节点拾取和镜头聚焦。
- 不默认自动旋转；用户可以主动开启。
- 首个可用版本先保证聚焦路径和证据审计可靠，再放开大规模全景浏览。

## 3. 目标与非目标

### 3.1 目标

- 让用户在三次交互内从结论打开对应的精确原始证据。
- 让用户从事件查看全部受影响结论及其支持、反驳、限定或解释关系。
- 对 AI 生成的节点和边保留证据、置信度、模型元数据、生成时间和审核历史。
- 提供稳定、可版本化、可重新生成的溯源数据模型。
- 在图数据库不可用时，仍能从 PostgreSQL 查看受限的聚焦路径。
- 在支持 WebGL 的浏览器中提供真正的三维深度、遮挡、透视相机和射线拾取。

### 3.2 非目标

- 不替换现有实体知识图谱。
- 不在第一版实现无限规模的全量图一次性渲染。
- 不让大模型在没有证据锚点时生成“已支持”的结论或关系。
- 不把语义相似直接解释为因果关系或确定来源。
- 不在 3D 场景中显示长篇原文；长文本放在审计抽屉中。
- 不默认允许拖动节点改变事实布局；拖拽手势用于相机操作，避免用户误改稳定空间结构。

## 4. 三层语义

### 4.1 结论层

结论层使用统一的 `Conclusion` 基础模型，按 `conclusion_type` 区分：

- `investment`：利好/利空、支持/削弱投资逻辑、风险判断、行动建议。
- `research`：可验证断言、因果解释、比较判断、趋势判断、RAG 或深度研究结论。

结论状态拆成两个维度，避免把“审核状态”和“证据结论”混成一个字段：

- `review_status`：`ai_generated | pending_review | confirmed | rejected`。
- `validation_status`：`unverified | supported | refuted | conflicted | insufficient_evidence`。

结论必须保留 `confidence`、有效时间范围、生成来源、模型/提示词版本和版本链。被新结论替代时使用 `supersedes_id`，不覆盖旧记录。

### 4.2 事件/事实层

中层允许三类节点并存：

- `event`：规范化事件，表达“谁在何时对什么做了什么”。
- `fact`：可被原文直接核验的陈述。
- `signal`：跨来源重复出现、尚未完全证实的聚合信号。

`KnowledgeEvent` 保存主体实体、动作、对象、发生时间、地点、事件类型和 `canonical_key`。事件归并需要同时考虑实体、时间窗、动作和语义；无法确定时建立候选关联，不强制合并。

现有 `InvestmentFact`、`InvestmentSignal` 和 `MacroEvent` 继续保留，由图注册表映射到中层。第一版不要求一次性迁移全部旧数据。

### 4.3 证据层

`EvidenceAnchor` 是不可变的细粒度证据锚点。它引用原始内容版本，而不是只引用当前文档。

支持的定位类型：

- `text_span`：`chunk_id + start_offset + end_offset`。
- `pdf_region`：`page_no + normalized_bbox`。
- `media_segment`：`start_ms + end_ms`。
- `image_region`：`image/frame id + normalized_bbox + OCR block ids`。
- `web_fragment`：稳定片段标识、DOM/文本定位快照和抓取时间。

每个锚点保存原文摘录、内容哈希、来源 URI 快照、来源质量、创建方式和校验状态。原文变化时标记 `stale`，保留旧摘录与哈希，不静默迁移到新内容。

### 4.4 关系方向与类型

规范方向始终从“依据”指向“被影响对象”：

```text
EvidenceAnchor -> Event / Fact / Signal -> Conclusion
```

查询可以反向遍历，但数据库不反转边。

主要关系类型：

- `supports`：支持。
- `refutes`：反驳。
- `qualifies`：限定适用范围或强度。
- `explains`：解释。
- `causes`：因果；需要比 `explains` 更高的证据门槛。
- `derived_from`：从证据抽取。
- `aggregates`：多个事实聚合成信号或事件。
- `related_unconfirmed`：相关但尚未确认。

每条 AI 生成的边必须关联至少一个 `EvidenceAnchor`，并保存 `confidence`、`rationale`、`origin_type`、模型元数据和审核状态。

## 5. PostgreSQL 数据模型

PostgreSQL 是溯源事实源。KuzuDB 或 NebulaGraph 只保存可重建的查询投影。

### 5.1 `evidence_anchor`

核心字段：

```text
id, workspace_id
document_id, version_id, chunk_id, source_item_id
anchor_type, locator_json
quote, content_hash, source_uri_snapshot
source_quality, validation_state
created_by_type, created_by_id
created_at
```

约束：

- `locator_json` 必须通过按 `anchor_type` 区分的 Pydantic 判别联合校验。
- 文本偏移、时间段和区域框必须合法且在来源边界内。
- 锚点创建后不修改定位和原文；重新锚定时创建新记录并链接旧锚点。

### 5.2 `knowledge_event`

核心字段：

```text
id, workspace_id
event_type, title, summary
subject_entity_ids, action, object_entity_ids
occurred_from, occurred_to, location
canonical_key, confidence
review_status, validation_status
origin_type, model_metadata
created_at, updated_at
```

`canonical_key` 用于幂等归并，不等于自动确认同一事件。冲突候选应保留独立记录和候选关联。

### 5.3 `conclusion`

核心字段：

```text
id, workspace_id
conclusion_type, conclusion_subtype
title, body, stance, scope_json
valid_from, valid_to, as_of
confidence, review_status, validation_status
origin_type, model_metadata
source_object_type, source_object_id
version_no, supersedes_id
created_at, updated_at
```

现有 `InvestmentClaim` 和 `InvestmentThesis` 通过兼容适配器映射为 `Conclusion`。新写入在同一数据库事务中更新通用结论和对应领域扩展，避免异步双写产生短暂不一致。研究 Agent 的 `ResearchClaim` 从临时输出升级为可持久化结论。

### 5.4 `trace_node`

`trace_node` 是稳定的图节点注册表：

```text
id, workspace_id
layer, node_type
backing_type, backing_id
label, occurred_at, confidence, display_status
properties_json
created_at, updated_at
```

`(workspace_id, backing_type, backing_id)` 唯一。`backing_id` 的领域完整性由注册服务验证，所有边端点通过外键引用 `trace_node.id`。节点 ID 必须稳定，不能随 AI 重跑或图同步变化。

### 5.5 `trace_edge`

核心字段：

```text
id, workspace_id
source_node_id, target_node_id
relation_type, rationale, confidence
review_status, validation_status
origin_type, model_metadata
version_no, supersedes_id
created_at, updated_at
```

边 ID 由端点、关系类型和版本语义稳定生成。重新推断不会覆盖已审核边，而是创建新版本并保留历史。

### 5.6 `trace_edge_evidence` 与 `trace_edge_review`

`trace_edge_evidence(edge_id, evidence_anchor_id)` 提供边到证据的强引用。

`trace_edge_review` 保存审核历史：审核人、原状态、新状态、决定、备注和时间。审核接口使用乐观锁版本号；版本冲突返回 HTTP 409。

## 6. 现有模型映射与迁移约束

| 现有对象 | 三层映射 | 处理方式 |
|---|---|---|
| `DocumentChunk` | 证据来源 | 生成 `EvidenceAnchor`，保留版本与偏移 |
| `VideoFrameAnalysis` | 图片证据来源 | 生成图片区域锚点，引用帧、区域框和 OCR 块 |
| YouTube transcript chunk | 音视频证据来源 | 生成时间段锚点 |
| `InvestmentItem` | 来源上下文 | 由锚点引用，不直接替代证据节点 |
| `InvestmentFact` | 事实节点 | 注册到中层并关联证据锚点 |
| `InvestmentSignal` | 信号节点 | 注册到中层并用 `aggregates` 关联事实 |
| `MacroEvent` | 事件节点 | 注册到中层，必要时归一为 `KnowledgeEvent` |
| `InvestmentClaim` | 投资结论 | 规范化为 `Conclusion(investment)` |
| `InvestmentThesis` | 投资结论/逻辑 | 规范化为 `Conclusion(investment)` |
| `ResearchClaim` | 研究结论 | 从临时 Schema 持久化为 `Conclusion(research)` |
| `InvestmentSourceTrace` | 来源关联 | 转换为 `related_unconfirmed` 或更高等级关系，不能自动视为确定来源 |

当前事实抽取和信号刷新逻辑存在删除后重建的行为，这会破坏图节点稳定 ID、审核记录和历史边。实现本功能前必须改为幂等 upsert：

- 事实键建议使用 `source_item_id + evidence_anchor_id + normalized_fact_hash`。
- 信号键建议使用稳定聚类键，不按每次运行重新分配 ID。
- 被新结果替代的记录标记为 inactive/superseded，不物理删除。

## 7. Schema-first 后端边界

在服务逻辑前定义以下 Pydantic v2 Schema：

- `EvidenceLocator` 判别联合及每种 locator 子类型。
- `EvidenceAnchorCreate/Response`。
- `KnowledgeEventCreate/Response`。
- `ConclusionCreate/Response`。
- `TraceLayer`、`TraceRelationType`、`TraceDirection`。
- `ProvenanceNode`、`ProvenanceEdge`、`ProvenanceGraphResponse`。
- `TraceEdgeReviewRequest/Response`。
- AI 专用 `FactEventExtractionOutput` 和 `ConclusionLinkOutput`，要求证据引用与置信度。

服务职责：

- `EvidenceAnchorService`：创建、边界校验、重新锚定和 stale 检测。
- `EventNormalizationService`：事件候选归一、去重和候选合并。
- `ConclusionService`：统一结论、版本和领域适配。
- `TraceRegistrationService`：稳定注册节点，校验 backing object。
- `TraceLinkService`：创建版本化边、验证层级和证据要求。
- `ProvenanceQueryService`：全景、上下行路径和 PostgreSQL 降级查询。
- `ProvenanceProjectionService`：向图存储同步可重建投影。

API 层只解析请求、执行工作区校验、调用服务并返回 Schema，不直接调用模型或拼装图数据。

## 8. API 设计

使用独立 `/api/v1/provenance` 路由：

```text
GET  /provenance/overview
GET  /provenance/nodes/{node_id}/trace?direction=up|down
GET  /provenance/edges/{edge_id}
POST /provenance/edges/{edge_id}/review
POST /provenance/conclusions
POST /provenance/rebuild
GET  /provenance/jobs/{job_id}
```

### 8.1 `GET /overview`

过滤条件包括工作区、时间窗、结论类型、节点状态、来源层级和最低置信度。响应包含：

- `nodes`、`edges`。
- `clusters` 和展开提示。
- `graph_version`。
- `degraded` 与 `degraded_reason`。
- 节点和边总量、当前返回量、是否存在更多数据。

### 8.2 `GET /nodes/{id}/trace`

- `direction=down`：结论到事件/事实再到证据。
- `direction=up`：证据或事件到受影响结论。
- 聚焦路径不能因为全景节点上限而静默截断。
- 若超过安全上限，响应返回明确的分页游标或聚合节点。

### 8.3 审核写入

`POST /edges/{id}/review` 支持 `confirm | reject | mark_conflict | reset_pending`，请求必须带当前 `version_no`。冲突使用统一错误结构返回：

```json
{
  "error": {
    "code": "trace_review_conflict",
    "message": "The trace edge changed before this review was saved.",
    "details": {"current_version": 4}
  }
}
```

### 8.4 异步重建

`POST /rebuild` 只创建 `task_job` 并立即返回 job ID。抽取、归一、结论链接和图投影均在 worker 中执行。

## 9. 异步生成流程

```text
来源解析
  -> 证据锚定
  -> 结构化事实/事件候选抽取
  -> 事件归一与聚类
  -> 结论生成或导入
  -> 支持/反驳/限定/解释关系生成
  -> 交叉验证与人工审核
  -> 图投影同步
```

规则：

1. 每一步由 `task_job` 跟踪输入、输出、进度和错误。
2. AI 输出必须通过 JSON Schema 校验。
3. 没有合法证据锚点时，不写入 AI 事实、结论关系或“已支持”状态。
4. 模型供应商通过现有抽象注入，不在服务中硬编码。
5. 无法归并的事件保留为候选，不静默丢弃。
6. 单个来源或单条记录失败不回滚其他已完成记录。
7. 重跑应幂等，并保留用户审核结果。

## 10. 前端页面与组件

新增独立页面，不把事件和结论塞进现有 `GraphPage` 的实体模式。

```text
ProvenanceGraphPage
  TraceModeToolbar
  SpatialLayerCanvas3D
    ProvenanceScene
    LayerPlane
    InstancedNodes
    TraceEdges
    FlowParticles
    CameraController
    LabelLayer
  GraphLegend
  EvidenceAuditDrawer
  ProvenanceFallbackView
```

- `ProvenanceGraphPage`：查询、URL 状态、模式、过滤、加载和错误。
- `SpatialLayerCanvas3D`：只负责三维绘制和画布事件。
- `EvidenceAuditDrawer`：展示长文本、证据定位、模型元数据和审核动作。
- `ProvenanceFallbackView`：WebGL 不可用时提供明确标识的二维/列表只读视图。

## 11. 真 3D 渲染设计

### 11.1 技术选择

- `three`：WebGL 场景、几何体、材质、相机、射线拾取。
- `@react-three/fiber`：把 Three.js 场景封装成 React 组件。
- `@react-three/drei`：使用受控 `OrbitControls` 和辅助组件。

现有 `@antv/g6` 继续服务二维实体图谱，不承担本功能的真 3D 渲染。

### 11.2 世界坐标

使用 Y 轴表示层级：

```text
Conclusion plane:  y = +H
Event/Fact plane:  y =  0
Evidence plane:    y = -H
```

节点在各自平面的 X/Z 坐标中布局，跨层边是实际三维线段。相机使用 `PerspectiveCamera`，因此旋转时会产生真实透视、遮挡和远近变化。

### 11.3 稳定布局

- 同一 `graph_version + filter + node_id` 使用确定性布局种子。
- 图层内布局放到 Web Worker，避免阻塞主线程。
- 节点初次出现可有入场动画，但已有节点重载后尽量保持原位置。
- 聚类节点展开时使用父节点位置作为初始中心，减少跳动。

### 11.4 渲染性能

- 大量同类节点使用 `InstancedMesh`。
- 边使用批量 line segments；只有选中路径使用流动粒子。
- 标签按 LOD 显示：远距仅显示簇与数量，中距显示重要节点，近距显示路径标签。
- 默认全景返回聚类结果；聚焦路径保留完整性。
- 无交互和无动效时使用按需渲染；动效期间进入连续帧循环。
- 根据设备性能降低 DPR、关闭阴影或减少粒子，不改变数据语义。
- 组件卸载时释放 geometry、material、texture 和控制器监听器。

## 12. 手势、键盘与镜头

已确认的鼠标手势：

- 左键拖动：环绕旋转。
- `Shift + 左键`、中键或右键拖动：上下左右平移。
- 鼠标滚轮：以光标附近为目标放大缩小。
- 单击节点：射线拾取节点，聚焦并高亮上下游路径。
- 单击边：打开边的证据与审核详情。
- 双击空白：恢复全景相机。

约束：

- 设置最小和最大相机距离，避免穿过图层或无限远离。
- 限制极端俯仰角，降低上下颠倒后的迷失感。
- 右键拖动时阻止浏览器原生上下文菜单。
- 镜头状态写入 URL 或页面 store，返回页面时可恢复。

键盘替代：

- 方向键平移。
- `+/-` 缩放。
- `R` 恢复全景。
- `Esc` 清除选择。
- 可通过节点列表聚焦节点，不要求用户只能操作 3D 画布。

## 13. 动效

- 页面进入：三层平面和节点分批出现，约 500–700ms。
- 节点聚焦：相机以约 450ms ease-out 飞向目标。
- 路径高亮：无关节点和边渐隐，约 180ms。
- 选中路径：少量粒子按规范方向流动，反驳边使用红色虚线/反向色彩提示。
- 全景自动旋转：默认关闭，由用户主动开启。
- 不让整张图所有边持续流动或闪烁。
- `prefers-reduced-motion` 启用时关闭入场、漂浮、路径粒子和镜头飞行动效，状态变化仍立即可见。

## 14. 信息密度与视觉编码

层颜色：

- 结论层：橙/金。
- 事件/事实层：蓝。
- 证据层：紫。

关系编码：

- 已确认支持：实线。
- AI 推断或未确认：虚线。
- 反驳/冲突：红色。
- 限定：琥珀色。
- 无关内容：选中节点后降至约 10–20% 透明度，不立即移除，保持空间方位感。

状态不能只依赖颜色；边型、图标、标签和审计抽屉必须同时说明含义。

## 15. 失败与降级

### 15.1 图存储不可用

`ProvenanceQueryService` 从 PostgreSQL 的 `trace_node/trace_edge` 查询受限的 1–2 跳路径，响应设置 `degraded=true`。前端显示降级横幅，不伪装成完整全景。

### 15.2 WebGL 不可用

显示明确的 WebGL 不可用提示，并切换到只读二维分层/列表视图。降级不能静默发生，避免用户误以为二维视图是真 3D。

### 15.3 证据失效

来源更新或内容哈希变化后，锚点标记为 `stale`。旧结论和审核历史保留，但不得自动继续显示为新版本已确认。

### 15.4 AI 输出无效

结构化输出有限重试后失败，`task_job` 标记失败。服务不能写入半成品节点、无证据边或空结论。

### 15.5 部分流水线失败

保留已完成阶段，记录失败步骤，允许从失败步骤重跑。前端展示部分结果与失败状态，不清空整张图。

### 15.6 数量超限

全景使用聚类、游标和 LOD。聚焦路径不能静默截断；如路径本身超过上限，API 返回显式聚合节点或分页信息。

## 16. 安全、隔离与审计

- 所有查询、节点注册、边写入和审核操作必须校验 `workspace_id`。
- 锚点只返回用户有权访问的原文。
- 错误响应不包含本地绝对存储路径、密钥、模型凭据或完整堆栈。
- 审核记录不可由普通更新接口覆盖或删除。
- AI 模型元数据保存 provider/model 标识、提示词版本和生成时间，但不保存密钥。
- 来源 URI 和原文摘录遵守现有敏感级别与文档可见性规则。

## 17. 测试策略

### 17.1 后端单元测试

- 每种 `EvidenceLocator` 的合法与非法边界。
- 无证据锚点的 AI 节点或边拒绝写入。
- 稳定节点 ID 和幂等 upsert。
- 事件候选归一、冲突保留和不确定关系。
- 边关系方向和跨层约束。
- 结论版本、supersede 和审核历史。
- 工作区隔离。

### 17.2 后端集成测试

- Alembic 升级和必要的降级验证。
- `overview`、上下行 `trace`、边详情和审核 API。
- 图投影与 PostgreSQL 结果一致性。
- 图存储不可用时的 PostgreSQL 降级。
- 审核乐观锁冲突返回 409。
- 异步 job 失败、重试和幂等。

### 17.3 前端组件测试

- 模式切换、筛选器、图例和审计抽屉。
- 节点/边状态到颜色、线型、图标的映射。
- 空态、部分失败、降级横幅和 stale 证据。
- `prefers-reduced-motion`。
- WebGL 不可用时的明确回退。

### 17.4 浏览器真 3D 测试

jsdom 不能证明 WebGL 行为，因此使用 Playwright 在真实浏览器上下文验证：

- WebGLRenderer 成功创建并至少渲染一帧。
- 左键拖动后相机 quaternion 变化。
- 平移后 controls target 变化。
- 滚轮后相机到 target 的距离变化。
- Raycaster 选中节点后审计抽屉更新。
- 双击空白恢复已保存的相机状态。
- 100、500、2000 原始节点夹具下的聚类、LOD、选中路径和资源释放。

测试应读取可测试的相机/选择控制器状态，而不是只比较像素截图。

## 18. 验收标准

1. 支持投资结论和通用研究结论。
2. 用户可从结论向下查看事件/事实和精确证据，也可从事件向上查看全部相关结论。
3. 段落、PDF 页与区域、音视频时间段、图片区域均能作为证据锚点打开。
4. 已确认、AI 推断、待审核、被驳回和冲突状态均可见且不只依赖颜色。
5. AI 生成的结论关系缺少合法证据锚点时不能入库。
6. 画布使用真实 WebGL 三维场景，旋转时具有透视、深度遮挡和远近变化。
7. 左键旋转、组合键/中键/右键平移、滚轮缩放、节点拾取和双击复位均通过浏览器测试。
8. 从任意结论在三次交互内打开对应原始证据。
9. 图存储离线时仍能查看受限聚焦路径，并明确显示降级状态。
10. WebGL 不可用时显示明确的二维只读回退，不伪装成 3D。
11. 重跑流水线不会改变稳定节点 ID 或覆盖人工审核历史。
12. 后端 `ruff check .`、`mypy app`、`pytest` 和前端 `npm run lint`、`npm run test`、`npm run build` 通过。

## 19. 分阶段交付

### 阶段 1：可审计数据基础

- Pydantic Schema、Alembic 模型、证据锚点、稳定节点/边和审核历史。
- 现有事实、信号、观点和研究结论适配。
- 聚焦路径 API 和 PostgreSQL 降级查询。

### 阶段 2：真 3D 聚焦路径

- `SpatialLayerCanvas3D`、相机控制、节点/边拾取。
- 结论向下和事件向上两种模式。
- 证据审计抽屉和原文定位。
- WebGL 与可访问性回退。

### 阶段 3：空间全景与动效

- 聚类全景、确定性布局、LOD 和 Web Worker。
- 路径粒子、镜头过渡和可选自动旋转。
- 大数据量性能自适应。

### 阶段 4：交叉验证与质量提升

- 支持/反驳/限定关系的自动交叉验证。
- stale 证据重新锚定工作流。
- 性能基线、真实数据视觉 QA 和使用指标。

## 20. 已知限制

- 真 3D 会比二维图消耗更多 GPU 和电量，低性能设备需要自动降级渲染质量。
- 大量长标签不适合直接放入三维场景，必须依赖 LOD、悬停和审计抽屉。
- 自动事件归并和因果识别无法只靠语义相似，需要时间、实体和证据规则共同约束。
- 外部网页可能变化或消失，因此锚点必须保存摘录、哈希和采集快照信息。
- 第一版全景不会保证同时展示全部原始节点，而是保证被选中溯源路径完整可审计。

## 21. 设计依据

- Three.js `OrbitControls` 官方文档：<https://threejs.org/docs/pages/OrbitControls.html>
- React Three Fiber 事件系统：<https://r3f.docs.pmnd.rs/api/events>
- React Three Fiber 性能扩展：<https://r3f.docs.pmnd.rs/advanced/scaling-performance>
