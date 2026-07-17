# 模型管理设计规格

**日期：** 2026-07-17  
**状态：** 已确认  
**范围：** 平台级模型提供商、模型配置、能力路由、密钥管理与连通性测试。

## 目标

KnowPilot 的 LLM、Embedding、ASR 与 OCR 不再分别从运行环境读取地址、模型名与 API Key。管理员可在“设置 → 模型管理”中维护这些配置，为每项能力选择一个默认模型，并在保存前验证连接。

本期只管理平台 AI 模型；不迁移 Tavily、YouTube、FRED 等非模型第三方服务凭据，也不提供按用户或工作区覆盖的模型路由。

## 用户体验

模型管理页面分为三个区域：

1. **提供商**：创建、编辑、启用或停用提供商。字段包括名称、协议、服务地址、超时和 API Key。
2. **模型**：为提供商添加模型，标记其单一能力（LLM、Embedding、ASR、OCR）及可选能力参数。模型可独立启停。
3. **默认路由**：四项能力各选择一个已启用模型。路由修改立即影响后续请求与后台任务，不影响正在执行的任务。

新增或编辑提供商时，API Key 可以留空以保留已保存密钥。页面只展示“未配置”或掩码（例如 `sk-…9x7k`），绝不回显完整值。

“测试连接”使用表单内的当前地址、模型和 API Key 发起一个最小真实请求，结果显示为：成功、网络/地址失败、鉴权失败、协议错误或能力不匹配。测试不保存输入内容，可能产生极小的模型调用费用。

## 数据模型

现有 `model_provider` 和 `model_config` 是本功能的基础，迁移会扩展而非重建它们：

### `model_provider`

- `name`：管理界面显示名。
- `provider_type`：协议枚举：`openai_compatible`、`glm_asr`、`knowpilot_ocr`。
- `base_url`：数据库保存的模型服务地址。
- `api_key_ciphertext`：Fernet 加密后的 API Key；仅服务端读取。
- `api_key_hint`：由服务端生成的掩码，供界面显示。
- `timeout_seconds`：单次模型请求超时。
- `enabled`、`last_test_status`、`last_test_message`、`last_tested_at`：可用性和最近测试记录。
- 旧的 `api_key_ref` 保留为兼容字段，不作为新写入路径。

### `model_config`

- `provider_id`、`model_name`、`model_type`、`enabled` 保持现有语义。
- `model_type` 收敛为 `llm`、`embedding`、`asr`、`ocr`。
- 已有上下文、输出长度与能力字段继续用于 LLM；ASR/OCR 可通过 `metadata` 保存协议特有参数。

### `model_route`

新增表，每项能力一行：`capability`（唯一）、`model_config_id`、`updated_at`。路由只能指向同能力、已启用模型及其已启用提供商。

## 密钥安全

应用新增必填部署密钥 `MODEL_ENCRYPTION_KEY`。它是 Fernet 密钥，仅存在于部署环境或密钥管理系统中，绝不保存到数据库、提交到仓库或返回给前端。

所有 API Key 在进入服务层后立即加密；日志、验证错误、测试结果和 API 响应都不得包含原值。读取密钥只发生在模型解析与测试连接的短生命周期内。缺少 `MODEL_ENCRYPTION_KEY` 时，任何包含新 API Key 的保存请求必须显式失败；不允许降级为明文存储。

## 运行时解析

新增 `ModelResolver` 作为唯一的数据库配置入口：

- LLM：研究、实体/关系抽取、陪读、YouTube 摘要和投资分析都使用默认 `llm` 路由。
- Embedding：RAG 索引与检索使用默认 `embedding` 路由。
- ASR：YouTube 无字幕回退使用默认 `asr` 路由。
- OCR：YouTube 视觉分析与投资网页图片 OCR 使用默认 `ocr` 路由。

数据库中未配置对应路由时，保留当前 `.env` 配置作为开发和首次部署的兼容兜底。生产环境的 `MODEL_ENCRYPTION_KEY` 仍必须通过环境或部署密钥注入；它不是模型业务配置。

为保持 API 依赖与后台任务一致，依赖工厂和 worker 都从数据库 session 取得解析结果。后台任务在任务开始时解析一次配置，避免任务中途因路由调整而切换模型。

## API

在 `/api/v1/model-management` 下提供：

- `GET/POST /providers`、`GET/PATCH/DELETE /providers/{id}`。
- `POST /providers/test`：测试未保存的提供商与选定模型表单。
- `GET/POST /models`、`PATCH/DELETE /models/{id}`。
- `GET/PUT /routes`：读取和更新四项默认路由。

删除被默认路由使用的模型或包含模型的提供商返回 `409 Conflict`。所有响应使用不含密文和明文密钥的 Pydantic 视图模型。

## 测试与验收

- 模型 API Key 的密文存储、掩码响应、空值保留旧密钥与缺失主密钥拒绝写入。
- 提供商、模型和路由 CRUD；禁用/能力不匹配/删除默认模型的约束。
- 测试连接针对四种协议的请求构造与错误分类，使用 `httpx` mock，不访问真实模型服务。
- LLM、Embedding、ASR、OCR 调用工厂优先使用数据库路由，未配置时才回退 `.env`。
- 模型管理页面的新增、测试结果、密钥掩码和默认路由交互测试。
- 后端 pytest、Ruff、相关 mypy；前端 test、lint、build。
