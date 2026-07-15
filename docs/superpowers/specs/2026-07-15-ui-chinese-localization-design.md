# 全平台中文化设计

## 目标

将 KnowPilot 平台中用户可见的英文界面文本统一转换为中文，让日常使用不再被英文状态、标签、按钮、占位符和错误信息打断。

本次中文化覆盖全平台用户界面，包括 YouTube、投资工作台、导入中心、阅读、知识图谱、研究、通用错误提示和各类状态展示。

## 非目标

- 不翻译用户采集到的原始内容，例如推文正文、YouTube 原字幕、网页标题、网页原文和引用摘录。
- 不修改数据库枚举值、API 字段名、接口协议和任务类型。
- 不把模型名、API 名、URL、日志字段、技术调试信息改成中文。
- 不重构页面结构，不新增大功能。

## 推荐方案

采用前端集中中文化层。

后端继续返回稳定的英文枚举值和技术错误信息，前端负责把用户可见值格式化为中文。新增或完善统一的显示工具，例如：

- `formatSourceType(value)`
- `formatStatus(value)`
- `formatImportance(value)`
- `formatInfoLayer(value)`
- `formatVerificationStatus(value)`
- `formatCollectorStatus(value)`
- `formatErrorMessage(error)`

页面只使用这些格式化函数展示文本，不直接把后端枚举值渲染给用户。

这样可以保持接口稳定，避免数据库迁移风险，也方便后续补充新状态的中文显示。

## 范围

### 通用界面

- 导航、页面标题、按钮、表格列名、筛选器、空状态和提示语。
- 表单占位符中的英文示例，替换为中文示例或中性 URL 示例。
- Ant Design 组件中用户可见的状态、确认提示、成功/失败消息。

### YouTube 模块

- 视频处理状态：`pending`、`processing`、`completed`、`failed`、`unknown`。
- 失败阶段：`capture`、`transcript`、`summary`、`pending`、`processing`。
- 字幕来源：`manual`、`auto`。
- 视觉资料类型、脑图编辑提示、重试按钮和历史列表状态。
- 常见 ASR/下载/摘要错误前缀中文化，保留原始错误细节。

### 投资模块

- 信息层级：`primary_source`、`macro_calendar`、`news`、`opinion`。
- 来源类型：`official`、`x_api`、`x_web`、`youtube`、`rss`、`manual` 等。
- 可信度：`official`、`reputable_media`、`personal_opinion`、`unknown`。
- 影响方向：`supports`、`weakens`、`contradicts`、`unrelated`、`unknown`。
- 重要性：`low`、`medium`、`high`。
- 操作状态：`pending_review`、`tracking`、`researched`、`ignored`。
- 采集器状态：`ready`、`auth_required`、`challenge_required`、`uninitialized`。
- 信号、事实、假设、待验证观点中的类型和状态显示。

### 其它模块

- 导入中心中的 `source_type`、`parse_status` 展示。
- 阅读、知识图谱、实体、RAG、研究页中直接展示给用户的英文标签。
- 通用错误展示层中的英文错误，例如 `not found`、`network error`、`request failed`。

## 数据流

1. 后端 API 返回原始数据和英文枚举值。
2. 前端 service/type 层保留原始类型定义。
3. 页面渲染时调用 `frontend/src/utils/localization.ts` 中的格式化函数。
4. 未知值显示为中文兜底，例如 `未知状态`，必要时附带原始值。
5. 错误提示优先显示后端中文 `detail`；如果是英文错误，则通过错误映射转换为中文，并在需要时附带原始信息。

## 错误处理

错误信息采用两层展示：

- 面向用户的中文摘要，例如 `视频下载失败`、`转写服务连接失败`、`请求失败`。
- 原始技术细节作为补充，例如括号内或详情区域，便于排障。

示例：

```text
转写服务连接失败：Connection refused
```

这样用户能先理解问题类型，开发和运维仍能看到原始错误。

## 组件设计

新增或完善：

- `frontend/src/utils/localization.ts`：通用枚举与错误中文化工具。
- `frontend/src/components/LocalizedStatusTag.tsx`（可选）：如果多个页面重复展示状态标签，再抽成组件。

优先使用函数，不急着新增复杂组件。只有当重复标签样式明显增多时再抽组件。

## 测试策略

### 前端测试

- 为 `localization.ts` 增加单元测试，覆盖常见枚举和未知值。
- 更新关键页面测试，确保页面展示中文，不再直接出现英文枚举。
- 覆盖 YouTube 和投资模块，因为它们是当前最常用路径。

### 后端测试

后端不改协议，原则上不需要新增大量后端测试。若发现后端直接返回用户提示且为英文，可补充针对错误 `detail` 的测试。

### 验证命令

```bash
cd frontend
npm run lint
npm run test
npm run build

cd ../backend
pytest
ruff check .
```

## 验收标准

- 平台主要页面不再直接展示英文枚举值。
- YouTube、投资工作台、导入中心、阅读、知识图谱、研究页的按钮、标签、状态和空状态为中文。
- 原始内容仍保持原文，不被错误翻译。
- 常见英文错误有中文摘要。
- 前端 lint、测试和 build 通过。
- 后端相关测试保持通过。

## 风险与规避

- 风险：把原文内容误翻译，影响信息真实性。
  - 规避：只翻译 UI 文案和枚举，不处理内容字段。
- 风险：遗漏新页面或少用页面的英文。
  - 规避：用 `rg` 扫描用户可见字符串，并在 `localization.ts` 建立兜底。
- 风险：未知枚举值显示生硬。
  - 规避：未知值显示 `未知状态` 或 `未知类型`，必要时附带原始值。
- 风险：错误信息过度翻译导致排障困难。
  - 规避：中文摘要加原始技术细节。

## 实施顺序

1. 建立 `localization.ts` 和单元测试。
2. 中文化投资模块。
3. 中文化 YouTube 模块。
4. 中文化导入、阅读、知识图谱、研究等页面。
5. 中文化通用错误展示。
6. 运行全量前端验证和相关后端验证。
