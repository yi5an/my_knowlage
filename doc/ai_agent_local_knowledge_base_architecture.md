# AI Agent 本地知识库工具技术架构设计文档

## 1. 文档说明

本文档从技术架构师角度，针对 AI Agent 本地知识库工具进行系统架构设计，覆盖：

- 开发语言选型
- 前后端技术栈
- 数据库选型
- 数据库表设计
- 图数据库设计
- 向量库设计
- 关键接口设计
- AI Agent 实现方式
- 模型支持方案
- 部署方案
- 技术风险与演进路线

本文档独立于产品 PRD。PRD 负责描述产品目标、用户场景和功能范围；本文档负责描述系统如何落地实现。

---

## 2. 技术架构目标

本项目不是单一 Web 系统，而是一个组合型 AI 知识系统，包含：

```text
文档处理系统
搜索系统
向量检索系统
知识图谱系统
AI Agent 系统
本地桌面应用
模型管理系统
```

架构目标：

1. **本地优先**：个人数据优先存储在本地，支持离线使用。
2. **可扩展**：后续可平滑升级为团队版、服务端版。
3. **模型可替换**：本地模型和云端模型都能接入。
4. **多数据库协同**：关系库、向量库、图数据库、全文索引各司其职。
5. **任务异步化**：文档解析、OCR、向量化、实体抽取、深度研究都走后台任务。
6. **结果可追溯**：AI 生成的摘要、实体、关系、回答必须绑定原文来源。
7. **接口清晰**：前端、后端、模型服务、数据库之间边界明确。
8. **隐私可控**：敏感资料默认走本地模型，不强制上传云端。

---

## 3. 总体技术架构

```text
┌────────────────────────────────────────────────────────────────────┐
│                         桌面端 / Web 前端                           │
│        Tauri / Electron + React + TypeScript + Ant Design           │
└───────────────────────────────┬────────────────────────────────────┘
                                │ REST / SSE / WebSocket
┌───────────────────────────────▼────────────────────────────────────┐
│                         后端 API 服务                               │
│                     Python FastAPI + Pydantic                       │
│                                                                    │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │ 文档服务     │ │ 搜索服务       │ │ 图谱服务       │ │ Agent 服务   │ │
│  └─────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │ 标注服务     │ │ 实体服务       │ │ 模型路由服务   │ │ 同步服务     │ │
│  └─────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │
└───────────────────────────────┬────────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────────┐
│                         后台任务系统                                │
│        Celery / Dramatiq / RQ + Redis，轻量版可用 SQLite Queue        │
│                                                                    │
│  文档解析任务 / OCR任务 / 向量化任务 / 实体抽取任务 / 关系抽取任务      │
│  图谱入库任务 / 深度研究任务 / NotebookLM 导出任务                    │
└───────────────────────────────┬────────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────────┐
│                         数据存储层                                  │
│                                                                    │
│  PostgreSQL / SQLite     文档元数据、用户数据、任务状态、标注         │
│  Qdrant / pgvector       向量检索、语义搜索、混合检索                 │
│  NebulaGraph / KuzuDB    实体、关系、图谱路径查询                    │
│  OpenSearch / ES / FTS   全文检索、关键词检索                         │
│  MinIO / 本地目录         原始文件、导出包、图片、附件                 │
└───────────────────────────────┬────────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────────┐
│                         模型服务层                                  │
│                                                                    │
│  Ollama / llama.cpp / vLLM       本地 LLM                            │
│  OpenAI / Gemini / Claude / GLM  云端 LLM                            │
│  PaddleOCR / MinerU / Marker     OCR 和 PDF 解析                     │
│  bge / gte / qwen embedding      Embedding                           │
│  bge-reranker / Jina reranker    重排序                               │
│  LLM + schema 校验              实体识别和关系抽取                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. 开发语言选型

## 4.1 后端语言：Python

### 4.1.1 推荐结论

后端核心建议使用：

```text
Python 3.11 / Python 3.12
```

### 4.1.2 选择原因

1. AI 生态最完整，LLM、Embedding、OCR、RAG、Agent、文档解析工具基本都优先支持 Python。
2. FastAPI 适合快速构建接口。
3. Pydantic 适合做 Schema-Driven Development。
4. Python 调用向量库、图数据库、OCR、LLM API 成本低。
5. 后续可以把性能敏感部分拆成独立服务。

### 4.1.3 后端技术栈

```text
Python 3.11 / 3.12
FastAPI
Pydantic v2
SQLAlchemy 2.x
Alembic
Celery / Dramatiq / RQ
Redis
httpx
LangGraph / 自研 Agent Workflow
LlamaIndex / Haystack / 自研 RAG Pipeline
```

### 4.1.4 不建议一开始用 Java / Go 做主后端

Java 和 Go 稳定性强，但本项目早期变化快，AI 工具链也以 Python 为主。早期用 Python 迭代效率最高。

后续可拆分：

| 模块 | 可选语言 |
|---|---|
| 主业务 API | Python |
| 高并发网关 | Go |
| 文件同步服务 | Go / Rust |
| 桌面端壳 | Rust / TypeScript |
| 图谱计算服务 | Python / Java / Scala |
| 模型推理服务 | Python / C++ |

---

## 4.2 前端语言：TypeScript

### 4.2.1 推荐结论

前端建议使用：

```text
React + TypeScript
```

### 4.2.2 选择原因

1. 图谱可视化、文档阅读器、标注交互都需要复杂前端状态管理。
2. TypeScript 能降低大型前端项目维护成本。
3. React 生态成熟，适合桌面端和 Web 端共用。

### 4.2.3 前端技术栈

```text
React
TypeScript
Vite
Zustand / Redux Toolkit
TanStack Query
React Router
Ant Design / Semi Design / shadcn/ui
TipTap / ProseMirror 文档编辑器
PDF.js PDF 阅读
ECharts / AntV G6 / Cytoscape.js 图谱展示
```

---

## 4.3 桌面端框架：Tauri 优先，Electron 备选

### 4.3.1 推荐结论

个人本地版优先选择：

```text
Tauri
```

### 4.3.2 选择原因

1. 安装包更小。
2. 资源占用低。
3. Rust 后端适合做本地文件访问、系统托盘、自动更新。
4. 前端仍然可以使用 React。

### 4.3.3 Electron 适合情况

如果团队更熟悉 Node.js，或者需要大量成熟桌面插件，可以选择 Electron。

### 4.3.4 推荐策略

```text
MVP：Web 版 + 本地 FastAPI 服务
桌面版：Tauri 包装前端 + 启动本地后端
团队版：独立 Web 前端 + 后端服务部署
```

---

## 5. 数据库选型

本项目不要试图用一个数据库解决所有问题。正确方式是：

```text
关系数据库 + 向量数据库 + 图数据库 + 全文搜索 + 文件存储
```

---

## 5.1 关系数据库

### 5.1.1 个人版推荐

```text
SQLite + FTS5
```

优点：

- 零部署。
- 本地文件即可备份。
- 适合个人知识库。
- 支持全文索引 FTS5。

缺点：

- 多用户并发能力一般。
- 大规模数据分析能力有限。

### 5.1.2 专业版推荐

```text
PostgreSQL
```

优点：

- 稳定成熟。
- 支持 JSONB。
- 支持全文检索。
- 可接 pgvector。
- 适合团队版和服务端版。

### 5.1.3 选型结论

| 版本 | 关系库 |
|---|---|
| 个人轻量版 | SQLite |
| 个人专业版 | PostgreSQL |
| 团队版 | PostgreSQL |

---

## 5.2 向量数据库

### 5.2.1 推荐：Qdrant

Qdrant 适合作为本项目主要向量数据库。

原因：

1. 支持本地部署和服务端部署。
2. 支持 payload 过滤。
3. 支持 dense vector、sparse vector、multi-vector 等能力。
4. 适合做语义搜索、混合搜索和 RAG 检索。

### 5.2.2 备选：pgvector

如果希望减少组件数量，可以先用 PostgreSQL + pgvector。

适合：

- MVP。
- 数据量不大。
- 运维简单优先。

不足：

- 复杂混合检索和大规模向量检索能力不如专业向量库。

### 5.2.3 备选：Chroma

适合快速原型，但长期稳定性、过滤能力和生产部署建议谨慎。

### 5.2.4 选型结论

```text
MVP：PostgreSQL + pgvector 或 Qdrant Local
正式版：Qdrant
```

---

## 5.3 图数据库

### 5.3.1 推荐方案一：KuzuDB

适合个人本地版。

优点：

- 嵌入式图数据库。
- 部署简单。
- 适合本地应用。
- 不需要单独启动复杂服务。

适合场景：

- 个人知识图谱。
- 中小规模实体关系。
- 本地桌面应用。

### 5.3.2 推荐方案二：NebulaGraph

适合专业版和大规模图谱。

优点：

- 分布式能力强。
- 适合大规模实体关系。
- 用户已有 NebulaGraph 使用经验。

缺点：

- 部署和运维复杂度较高。
- 对个人本地桌面版偏重。

### 5.3.3 推荐方案三：Neo4j

适合可视化和生态。

优点：

- Cypher 生态成熟。
- 图可视化和社区资料丰富。

缺点：

- 本地嵌入式和授权策略需要提前评估。

### 5.3.4 选型结论

| 版本 | 图数据库 |
|---|---|
| MVP / 单机版 | KuzuDB 或 PostgreSQL 边表 |
| 专业个人版 | KuzuDB / Neo4j |
| 团队版 / 大规模版 | NebulaGraph |

---

## 5.4 全文搜索

### 5.4.1 轻量版

```text
SQLite FTS5 / PostgreSQL Full Text Search
```

### 5.4.2 专业版

```text
OpenSearch / Elasticsearch
```

考虑用户已有 Elasticsearch 使用经验，专业版可以支持 Elasticsearch / OpenSearch。

### 5.4.3 搜索架构建议

不要只做向量搜索。知识库搜索应该是混合检索：

```text
关键词 BM25
  +
向量语义搜索
  +
实体图谱权重
  +
用户行为权重
  +
Reranker 重排序
```

---

## 5.5 文件存储

### 5.5.1 个人版

```text
本地文件目录
```

目录结构示例：

```text
~/.knowpilot/
  data/
    files/
      original/
      parsed/
      exports/
      thumbnails/
    db/
    models/
    logs/
```

### 5.5.2 专业版

```text
MinIO
```

适合存储：

- 原始文档。
- 解析后的 Markdown。
- 图片。
- OCR 中间文件。
- NotebookLM 导出资料包。
- 深度研究报告附件。

---

# 6. 数据库表设计

以下以 PostgreSQL 为主设计。SQLite 版本可以做字段裁剪。

---

## 6.1 用户与空间表

### 6.1.1 workspace

```sql
CREATE TABLE workspace (
  id VARCHAR(64) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  storage_mode VARCHAR(32) DEFAULT 'local',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 6.1.2 user_profile

```sql
CREATE TABLE user_profile (
  id VARCHAR(64) PRIMARY KEY,
  username VARCHAR(128),
  display_name VARCHAR(128),
  email VARCHAR(255),
  role VARCHAR(64) DEFAULT 'owner',
  created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 6.2 分类与标签表

### 6.2.1 category

```sql
CREATE TABLE category (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  parent_id VARCHAR(64),
  name VARCHAR(128) NOT NULL,
  level INT NOT NULL,
  path TEXT NOT NULL,
  sort_order INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT ck_category_level CHECK (level BETWEEN 1 AND 3)
);

CREATE INDEX idx_category_workspace_parent ON category(workspace_id, parent_id);
```

### 6.2.2 tag

```sql
CREATE TABLE tag (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  color VARCHAR(32),
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, name)
);
```

### 6.2.3 document_tag

```sql
CREATE TABLE document_tag (
  doc_id VARCHAR(64) NOT NULL,
  tag_id VARCHAR(64) NOT NULL,
  PRIMARY KEY(doc_id, tag_id)
);
```

---

## 6.3 文档主表

### 6.3.1 document

```sql
CREATE TABLE document (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  title TEXT NOT NULL,
  source_type VARCHAR(64) NOT NULL,
  source_uri TEXT,
  file_id VARCHAR(64),
  category_id VARCHAR(64),
  content_type VARCHAR(128),
  language VARCHAR(32),
  summary TEXT,
  ai_summary TEXT,
  status VARCHAR(32) DEFAULT 'created',
  parse_status VARCHAR(32) DEFAULT 'pending',
  index_status VARCHAR(32) DEFAULT 'pending',
  entity_status VARCHAR(32) DEFAULT 'pending',
  relation_status VARCHAR(32) DEFAULT 'pending',
  content_hash VARCHAR(128),
  sensitive_level VARCHAR(32) DEFAULT 'normal',
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_document_workspace ON document(workspace_id);
CREATE INDEX idx_document_category ON document(category_id);
CREATE INDEX idx_document_status ON document(status, parse_status);
CREATE INDEX idx_document_metadata_gin ON document USING GIN(metadata);
```

### 6.3.2 document_file

```sql
CREATE TABLE document_file (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  original_name TEXT NOT NULL,
  storage_backend VARCHAR(32) DEFAULT 'local',
  storage_path TEXT NOT NULL,
  mime_type VARCHAR(128),
  file_size BIGINT,
  sha256 VARCHAR(128),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_document_file_sha ON document_file(workspace_id, sha256);
```

---

## 6.4 文档版本与正文表

### 6.4.1 document_version

```sql
CREATE TABLE document_version (
  id VARCHAR(64) PRIMARY KEY,
  doc_id VARCHAR(64) NOT NULL,
  version_no INT NOT NULL,
  title TEXT,
  content_md TEXT NOT NULL,
  content_text TEXT,
  change_summary TEXT,
  content_hash VARCHAR(128),
  created_by VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(doc_id, version_no)
);

CREATE INDEX idx_document_version_doc ON document_version(doc_id, version_no DESC);
```

### 6.4.2 document_chunk

```sql
CREATE TABLE document_chunk (
  id VARCHAR(64) PRIMARY KEY,
  doc_id VARCHAR(64) NOT NULL,
  version_id VARCHAR(64) NOT NULL,
  chunk_index INT NOT NULL,
  heading TEXT,
  content TEXT NOT NULL,
  content_hash VARCHAR(128),
  page_no INT,
  start_offset INT,
  end_offset INT,
  token_count INT,
  vector_id VARCHAR(128),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(version_id, chunk_index)
);

CREATE INDEX idx_chunk_doc ON document_chunk(doc_id);
CREATE INDEX idx_chunk_version ON document_chunk(version_id);
CREATE INDEX idx_chunk_metadata_gin ON document_chunk USING GIN(metadata);
```

---

## 6.5 标注与备注表

### 6.5.1 annotation

```sql
CREATE TABLE annotation (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  doc_id VARCHAR(64) NOT NULL,
  version_id VARCHAR(64),
  chunk_id VARCHAR(64),
  annotation_type VARCHAR(32) NOT NULL,
  selected_text TEXT,
  note TEXT,
  color VARCHAR(32),
  start_offset INT,
  end_offset INT,
  page_no INT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_by VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_annotation_doc ON annotation(doc_id);
CREATE INDEX idx_annotation_type ON annotation(annotation_type);
```

---

## 6.6 实体类型与实体表

### 6.6.1 entity_type

```sql
CREATE TABLE entity_type (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  domain VARCHAR(128),
  description TEXT,
  examples JSONB DEFAULT '[]'::jsonb,
  aliases JSONB DEFAULT '[]'::jsonb,
  rules JSONB DEFAULT '[]'::jsonb,
  source VARCHAR(32) DEFAULT 'system',
  status VARCHAR(32) DEFAULT 'active',
  confidence FLOAT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, name)
);
```

### 6.6.2 entity

```sql
CREATE TABLE entity (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  entity_type_id VARCHAR(64) NOT NULL,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  aliases JSONB DEFAULT '[]'::jsonb,
  description TEXT,
  properties JSONB DEFAULT '{}'::jsonb,
  confidence FLOAT DEFAULT 0,
  verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_entity_workspace_type ON entity(workspace_id, entity_type_id);
CREATE INDEX idx_entity_normalized_name ON entity(workspace_id, normalized_name);
CREATE INDEX idx_entity_properties_gin ON entity USING GIN(properties);
```

### 6.6.3 entity_mention

```sql
CREATE TABLE entity_mention (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  entity_id VARCHAR(64) NOT NULL,
  doc_id VARCHAR(64) NOT NULL,
  chunk_id VARCHAR(64),
  mention_text TEXT NOT NULL,
  start_offset INT,
  end_offset INT,
  page_no INT,
  confidence FLOAT DEFAULT 0,
  extractor VARCHAR(64),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_entity_mention_entity ON entity_mention(entity_id);
CREATE INDEX idx_entity_mention_doc ON entity_mention(doc_id);
```

---

## 6.7 关系表

### 6.7.1 relation_type

```sql
CREATE TABLE relation_type (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  description TEXT,
  domain VARCHAR(128),
  source_entity_types JSONB DEFAULT '[]'::jsonb,
  target_entity_types JSONB DEFAULT '[]'::jsonb,
  examples JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, name)
);
```

### 6.7.2 entity_relation

```sql
CREATE TABLE entity_relation (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  source_entity_id VARCHAR(64) NOT NULL,
  target_entity_id VARCHAR(64) NOT NULL,
  relation_type_id VARCHAR(64) NOT NULL,
  evidence_doc_id VARCHAR(64),
  evidence_chunk_id VARCHAR(64),
  evidence_text TEXT,
  confidence FLOAT DEFAULT 0,
  verified BOOLEAN DEFAULT FALSE,
  properties JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_relation_source ON entity_relation(source_entity_id);
CREATE INDEX idx_relation_target ON entity_relation(target_entity_id);
CREATE INDEX idx_relation_type ON entity_relation(relation_type_id);
CREATE INDEX idx_relation_workspace ON entity_relation(workspace_id);
```

---

## 6.8 股票与产业链扩展表

股票和产业链也可以全部放在 `entity.properties` 中，但为了高频查询，建议增加扩展表。

### 6.8.1 stock_profile

```sql
CREATE TABLE stock_profile (
  entity_id VARCHAR(64) PRIMARY KEY,
  ticker VARCHAR(32) NOT NULL,
  exchange VARCHAR(64),
  currency VARCHAR(16),
  company_name TEXT,
  company_short_name TEXT,
  country VARCHAR(64),
  industry VARCHAR(128),
  sector VARCHAR(128),
  listing_status VARCHAR(32),
  metadata JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_stock_ticker ON stock_profile(ticker, exchange);
CREATE INDEX idx_stock_industry ON stock_profile(industry, sector);
```

### 6.8.2 industry_chain

```sql
CREATE TABLE industry_chain (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  domain VARCHAR(128),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 6.8.3 industry_chain_node

```sql
CREATE TABLE industry_chain_node (
  id VARCHAR(64) PRIMARY KEY,
  chain_id VARCHAR(64) NOT NULL,
  entity_id VARCHAR(64),
  name VARCHAR(255) NOT NULL,
  stage VARCHAR(64) NOT NULL,
  node_type VARCHAR(64),
  description TEXT,
  sort_order INT DEFAULT 0,
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_chain_node_chain_stage ON industry_chain_node(chain_id, stage);
```

### 6.8.4 industry_chain_edge

```sql
CREATE TABLE industry_chain_edge (
  id VARCHAR(64) PRIMARY KEY,
  chain_id VARCHAR(64) NOT NULL,
  source_node_id VARCHAR(64) NOT NULL,
  target_node_id VARCHAR(64) NOT NULL,
  relation_type VARCHAR(64),
  description TEXT,
  evidence_doc_id VARCHAR(64),
  confidence FLOAT DEFAULT 0,
  metadata JSONB DEFAULT '{}'::jsonb
);
```

---

## 6.9 任务表

### 6.9.1 task_job

```sql
CREATE TABLE task_job (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  job_type VARCHAR(64) NOT NULL,
  target_type VARCHAR(64),
  target_id VARCHAR(64),
  status VARCHAR(32) DEFAULT 'pending',
  progress INT DEFAULT 0,
  input JSONB DEFAULT '{}'::jsonb,
  output JSONB DEFAULT '{}'::jsonb,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_task_status ON task_job(status, job_type);
CREATE INDEX idx_task_target ON task_job(target_type, target_id);
```

---

## 6.10 深度研究表

### 6.10.1 research_task

```sql
CREATE TABLE research_task (
  id VARCHAR(64) PRIMARY KEY,
  workspace_id VARCHAR(64) NOT NULL,
  title TEXT NOT NULL,
  question TEXT NOT NULL,
  status VARCHAR(32) DEFAULT 'pending',
  plan JSONB DEFAULT '{}'::jsonb,
  report_doc_id VARCHAR(64),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 6.10.2 research_source

```sql
CREATE TABLE research_source (
  id VARCHAR(64) PRIMARY KEY,
  research_task_id VARCHAR(64) NOT NULL,
  source_type VARCHAR(64) NOT NULL,
  title TEXT,
  url TEXT,
  doc_id VARCHAR(64),
  snippet TEXT,
  credibility_score FLOAT,
  used_in_report BOOLEAN DEFAULT FALSE,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 6.11 模型配置表

### 6.11.1 model_provider

```sql
CREATE TABLE model_provider (
  id VARCHAR(64) PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  provider_type VARCHAR(64) NOT NULL,
  base_url TEXT,
  api_key_ref TEXT,
  enabled BOOLEAN DEFAULT TRUE,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 6.11.2 model_config

```sql
CREATE TABLE model_config (
  id VARCHAR(64) PRIMARY KEY,
  provider_id VARCHAR(64) NOT NULL,
  model_name VARCHAR(128) NOT NULL,
  model_type VARCHAR(64) NOT NULL,
  context_window INT,
  max_output_tokens INT,
  supports_vision BOOLEAN DEFAULT FALSE,
  supports_tools BOOLEAN DEFAULT FALSE,
  supports_json_schema BOOLEAN DEFAULT FALSE,
  enabled BOOLEAN DEFAULT TRUE,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

---

# 7. 图数据库设计

## 7.1 图节点

```text
Document
Chunk
Entity
EntityType
Category
Tag
Annotation
ResearchTask
ResearchSource
IndustryChain
Stock
```

## 7.2 图关系

```text
Document -[:HAS_CHUNK]-> Chunk
Document -[:BELONGS_TO]-> Category
Document -[:HAS_TAG]-> Tag
Document -[:MENTIONS]-> Entity
Chunk -[:MENTIONS]-> Entity
Entity -[:INSTANCE_OF]-> EntityType
Entity -[:RELATED_TO]-> Entity
Entity -[:SUPPLIES_TO]-> Entity
Entity -[:COMPETES_WITH]-> Entity
Entity -[:CUSTOMER_OF]-> Entity
Entity -[:UPSTREAM_OF]-> Entity
Entity -[:DOWNSTREAM_OF]-> Entity
Entity -[:LISTED_AS]-> Stock
Stock -[:BELONGS_TO_INDUSTRY]-> Entity
Annotation -[:ANNOTATES]-> Chunk
ResearchTask -[:USES_SOURCE]-> ResearchSource
ResearchTask -[:GENERATES]-> Document
```

## 7.3 NebulaGraph Tag 示例

```ngql
CREATE TAG entity(
  entity_id string,
  name string,
  type string,
  description string,
  properties string
);

CREATE TAG document(
  doc_id string,
  title string,
  source_type string
);

CREATE EDGE relation(
  relation_type string,
  evidence string,
  confidence double,
  verified bool
);

CREATE EDGE mentioned_in(
  doc_id string,
  chunk_id string,
  confidence double
);
```

## 7.4 图谱与关系库同步策略

关系库是主数据，图数据库是图查询加速层。

```text
PostgreSQL entity / relation 表
  ↓
Outbox Event
  ↓
Graph Sync Worker
  ↓
NebulaGraph / KuzuDB
```

优点：

1. 业务数据以关系库为准。
2. 图数据库可重建。
3. 避免双写不一致。
4. 方便回滚和审计。

---

# 8. 向量库设计

## 8.1 Collection 设计

推荐按 workspace 建 collection，或者统一 collection 用 workspace_id 过滤。

```text
collection: knowpilot_chunks
vector:
  dense_vector: 1024 / 768 / 1536 dims
  sparse_vector: BM25 / SPLADE sparse vector
payload:
  workspace_id
  doc_id
  version_id
  chunk_id
  title
  category_id
  tags
  entity_ids
  source_type
  created_at
  updated_at
  sensitive_level
```

## 8.2 检索流程

```text
用户问题
  ↓
Query Rewrite
  ↓
关键词检索 BM25
  ↓
向量检索 Dense Vector
  ↓
图谱扩展相关实体
  ↓
结果融合 RRF
  ↓
Reranker 重排序
  ↓
构造上下文
  ↓
LLM 生成答案
  ↓
返回答案 + 引用来源
```

## 8.3 Chunk 策略

默认策略：

```text
中文文档：500-800 字一个 chunk
英文文档：300-600 tokens 一个 chunk
重叠：80-120 字 / tokens
保留标题层级
保留页码
保留表格为 Markdown
代码块不轻易切断
```

特殊文档：

| 类型 | 策略 |
|---|---|
| PDF | 按页 + 章节混合切分 |
| Excel | 按 Sheet、表格区域、字段说明切分 |
| Word | 按标题层级切分 |
| 代码 | 按函数、类、配置段切分 |
| 研报 | 按章节、图表、观点切分 |

---

# 9. 关键接口设计

以下接口使用 REST 风格。长任务使用任务 ID + SSE/WebSocket 推送进度。

---

## 9.1 文档导入接口

### 9.1.1 上传文件

```http
POST /api/v1/documents/import/file
Content-Type: multipart/form-data
```

请求参数：

```text
file: 文件
workspace_id: 工作空间 ID
category_id: 可选
auto_parse: true
extract_entities: true
extract_relations: true
```

响应：

```json
{
  "doc_id": "doc_001",
  "job_id": "job_001",
  "status": "pending"
}
```

### 9.1.2 URL 导入

```http
POST /api/v1/documents/import/url
```

请求：

```json
{
  "workspace_id": "ws_001",
  "url": "https://example.com/article",
  "category_id": "cat_ai_agent",
  "options": {
    "auto_parse": true,
    "extract_entities": true,
    "extract_relations": true,
    "save_snapshot": true
  }
}
```

---

## 9.2 文档管理接口

### 9.2.1 文档列表

```http
GET /api/v1/documents?workspace_id=ws_001&category_id=cat_001&keyword=agent&page=1&page_size=20
```

### 9.2.2 文档详情

```http
GET /api/v1/documents/{doc_id}
```

### 9.2.3 获取文档版本内容

```http
GET /api/v1/documents/{doc_id}/versions/{version_id}
```

### 9.2.4 保存文档内容

```http
PUT /api/v1/documents/{doc_id}/content
```

请求：

```json
{
  "base_version_id": "ver_001",
  "title": "AI Agent 本地知识库 PRD",
  "content_md": "# 文档正文...",
  "change_summary": "修改实体识别章节"
}
```

响应：

```json
{
  "doc_id": "doc_001",
  "version_id": "ver_002",
  "reindex_job_id": "job_102"
}
```

---

## 9.3 标注接口

### 9.3.1 创建标注

```http
POST /api/v1/annotations
```

请求：

```json
{
  "workspace_id": "ws_001",
  "doc_id": "doc_001",
  "version_id": "ver_002",
  "chunk_id": "chunk_009",
  "annotation_type": "highlight",
  "selected_text": "GraphRAG 是核心技术路线之一",
  "note": "重点关注",
  "color": "yellow",
  "start_offset": 120,
  "end_offset": 156
}
```

### 9.3.2 查询文档标注

```http
GET /api/v1/documents/{doc_id}/annotations
```

---

## 9.4 搜索接口

### 9.4.1 混合搜索

```http
POST /api/v1/search
```

请求：

```json
{
  "workspace_id": "ws_001",
  "query": "GraphRAG 在本地知识库中的作用",
  "search_types": ["keyword", "vector", "graph", "annotation"],
  "filters": {
    "category_ids": ["cat_ai"],
    "entity_types": ["技术", "产品"],
    "source_types": ["pdf", "url"]
  },
  "top_k": 20,
  "rerank": true
}
```

响应：

```json
{
  "results": [
    {
      "doc_id": "doc_001",
      "chunk_id": "chunk_009",
      "title": "AI Agent 本地知识库 PRD",
      "snippet": "GraphRAG 是核心技术路线之一...",
      "score": 0.92,
      "source_type": "vector",
      "entities": ["GraphRAG", "RAG", "图数据库"]
    }
  ]
}
```

### 9.4.2 对话式问答

```http
POST /api/v1/chat/query
```

请求：

```json
{
  "workspace_id": "ws_001",
  "question": "我的知识库中 GraphRAG 主要和哪些技术相关？",
  "scope": {
    "category_ids": ["cat_ai"],
    "doc_ids": []
  },
  "answer_mode": "grounded",
  "include_graph_context": true
}
```

响应：

```json
{
  "answer": "GraphRAG 主要和 RAG、向量数据库、图数据库、实体关系抽取相关...",
  "citations": [
    {
      "doc_id": "doc_001",
      "chunk_id": "chunk_009",
      "text": "GraphRAG 是核心技术路线之一..."
    }
  ],
  "related_entities": ["GraphRAG", "RAG", "Qdrant", "NebulaGraph"]
}
```

---

## 9.5 实体接口

### 9.5.1 实体列表

```http
GET /api/v1/entities?workspace_id=ws_001&type=股票/证券&keyword=英伟达
```

### 9.5.2 实体详情

```http
GET /api/v1/entities/{entity_id}
```

### 9.5.3 创建或修改实体

```http
PUT /api/v1/entities/{entity_id}
```

请求：

```json
{
  "name": "英伟达",
  "entity_type": "股票/证券",
  "aliases": ["NVIDIA", "NVDA"],
  "properties": {
    "ticker": "NVDA",
    "exchange": "NASDAQ",
    "industry": "半导体",
    "sector": "AI 芯片"
  },
  "verified": true
}
```

### 9.5.4 自动发现实体类型

```http
POST /api/v1/entity-types/discover
```

请求：

```json
{
  "workspace_id": "ws_001",
  "doc_ids": ["doc_001", "doc_002"],
  "min_frequency": 5,
  "domain_hint": "投资研究"
}
```

响应：

```json
{
  "suggestions": [
    {
      "name": "财务指标",
      "domain": "投资研究",
      "examples": ["毛利率", "ROE", "自由现金流"],
      "confidence": 0.88,
      "reason": "这些词在多个公司分析文档中高频共现，且都用于衡量公司经营质量。"
    }
  ]
}
```

### 9.5.5 确认新增实体类型

```http
POST /api/v1/entity-types
```

---

## 9.6 图谱接口

### 9.6.1 查询节点邻居

```http
GET /api/v1/graph/entities/{entity_id}/neighbors?depth=1&limit=50
```

### 9.6.2 图谱搜索

```http
POST /api/v1/graph/search
```

请求：

```json
{
  "workspace_id": "ws_001",
  "query": "AI 算力产业链",
  "node_types": ["产业链", "公司", "产品", "股票/证券"],
  "depth": 2
}
```

### 9.6.3 路径查询

```http
POST /api/v1/graph/path
```

请求：

```json
{
  "workspace_id": "ws_001",
  "source_entity_id": "entity_nvda",
  "target_entity_id": "entity_tsmc",
  "max_depth": 3
}
```

---

## 9.7 深度研究接口

### 9.7.1 创建研究任务

```http
POST /api/v1/research/tasks
```

请求：

```json
{
  "workspace_id": "ws_001",
  "title": "AI Agent 知识库竞品分析",
  "question": "请分析 AI Agent 本地知识库产品的竞品、技术架构和商业化方向",
  "scope": {
    "use_local_kb": true,
    "use_web_search": true,
    "category_ids": ["cat_ai_agent"]
  },
  "output_options": {
    "generate_report": true,
    "extract_entities": true,
    "extract_relations": true
  }
}
```

响应：

```json
{
  "research_task_id": "research_001",
  "job_id": "job_900",
  "status": "pending"
}
```

### 9.7.2 获取研究进度

```http
GET /api/v1/research/tasks/{task_id}/progress
```

### 9.7.3 导入研究结果

```http
POST /api/v1/research/tasks/{task_id}/import
```

---

## 9.8 模型接口

### 9.8.1 模型列表

```http
GET /api/v1/models
```

### 9.8.2 测试模型

```http
POST /api/v1/models/test
```

### 9.8.3 模型路由配置

```http
PUT /api/v1/model-routing
```

请求：

```json
{
  "routes": [
    {
      "task_type": "embedding",
      "model_id": "bge_m3_local"
    },
    {
      "task_type": "deep_research",
      "model_id": "gpt_or_gemini_cloud"
    },
    {
      "task_type": "sensitive_summary",
      "model_id": "qwen_local"
    }
  ]
}
```

---

## 9.9 NotebookLM 对接接口

### 9.9.1 生成资料包

```http
POST /api/v1/notebooklm/export-package
```

请求：

```json
{
  "workspace_id": "ws_001",
  "category_id": "cat_ai_agent",
  "doc_ids": ["doc_001", "doc_002"],
  "format": "zip",
  "include_entities": true,
  "include_timeline": true,
  "include_questions": true
}
```

### 9.9.2 企业版创建 Notebook

```http
POST /api/v1/notebooklm/notebooks
```

请求：

```json
{
  "workspace_id": "ws_001",
  "provider": "google_enterprise",
  "display_name": "AI Agent 知识库研究",
  "source_package_id": "pkg_001"
}
```

---

# 10. 核心实现方式

## 10.1 文档导入实现

```text
用户上传文件
  ↓
保存原始文件
  ↓
计算 hash 去重
  ↓
创建 document 记录
  ↓
创建 parse job
  ↓
后台任务解析
  ↓
生成 Markdown 正文
  ↓
生成 document_version
  ↓
生成 chunk
  ↓
向量化入库
  ↓
全文索引
  ↓
实体识别
  ↓
关系抽取
  ↓
图数据库同步
```

解析器按文件类型分发：

```python
class DocumentParserRouter:
    def parse(self, file: FileObject) -> ParsedDocument:
        if file.mime_type == "application/pdf":
            return pdf_parser.parse(file)
        if file.mime_type in WORD_TYPES:
            return word_parser.parse(file)
        if file.mime_type in EXCEL_TYPES:
            return excel_parser.parse(file)
        if file.mime_type.startswith("image/"):
            return image_ocr_parser.parse(file)
        return text_parser.parse(file)
```

---

## 10.2 RAG 问答实现

```text
Question
  ↓
问题改写 Query Rewrite
  ↓
识别问题中的实体
  ↓
全文检索 BM25
  ↓
向量检索 Dense Search
  ↓
图谱扩展 Graph Expand
  ↓
结果融合 RRF
  ↓
Reranker 重排序
  ↓
上下文压缩
  ↓
LLM 生成答案
  ↓
引用来源校验
  ↓
返回答案
```

关键点：

1. 不允许无来源回答知识库问题。
2. 每段答案都尽量绑定引用。
3. 如果检索结果不足，明确提示“知识库中没有足够证据”。
4. 股票、财务、政策等时效性内容需要提示数据日期。

---

## 10.3 实体识别实现

采用多阶段管线：

```text
文本 Chunk
  ↓
规则识别
  ↓
词典识别
  ↓
LLM Schema 抽取
  ↓
实体标准化
  ↓
实体消歧
  ↓
实体合并建议
  ↓
写入 entity / entity_mention
```

LLM 输出必须使用 JSON Schema：

```json
{
  "entities": [
    {
      "name": "英伟达",
      "type": "股票/证券",
      "aliases": ["NVIDIA", "NVDA"],
      "properties": {
        "ticker": "NVDA",
        "exchange": "NASDAQ"
      },
      "evidence": "英伟达 NVDA 是全球 GPU 龙头公司",
      "confidence": 0.94
    }
  ]
}
```

---

## 10.4 关系抽取实现

关系抽取不要对全文一次性处理，而是基于 chunk + 实体共现处理。

```text
Chunk
  ↓
获取 chunk 内实体
  ↓
构造候选实体对
  ↓
LLM 判断关系
  ↓
Schema 校验
  ↓
关系类型规范化
  ↓
证据绑定
  ↓
写入 relation
```

关系抽取 Prompt 应限制：

1. 只能基于原文证据。
2. 不能凭常识补充关系。
3. 必须返回 evidence_text。
4. 必须返回 confidence。
5. 不确定则返回 none。

---

## 10.5 实体类型自动丰富实现

```text
未识别名词短语池
  ↓
频次统计
  ↓
Embedding 聚类
  ↓
过滤已有实体类型
  ↓
LLM 归纳类型名称
  ↓
生成候选 entity_type
  ↓
用户确认
  ↓
加入类型库
```

候选实体类型判断条件：

| 条件 | 建议阈值 |
|---|---|
| 候选实体数量 | ≥ 5 |
| 跨文档出现数量 | ≥ 3 |
| 聚类相似度 | ≥ 0.75 |
| LLM 置信度 | ≥ 0.8 |
| 用户确认 | 必须 |

---

## 10.6 图谱展示实现

前端图谱建议使用：

```text
AntV G6 / Cytoscape.js / Sigma.js
```

图谱渲染策略：

1. 默认最多显示 100-300 个节点。
2. 大图必须分页展开。
3. 节点按类型上色。
4. 边按关系类型区分。
5. 支持一跳和二跳展开。
6. 支持社区折叠。
7. 支持搜索定位节点。

后端接口只返回当前视图需要的子图，不一次返回全图。

---

## 10.7 深度研究实现

深度研究使用 Agent Workflow，不建议一开始做完全自由 Agent。

推荐固定流程：

```text
PlanResearchNode
  ↓
SearchLocalKnowledgeNode
  ↓
SearchWebNode
  ↓
ReadSourcesNode
  ↓
ExtractClaimsNode
  ↓
CrossCheckNode
  ↓
GenerateReportNode
  ↓
ImportToKnowledgeBaseNode
```

每个节点输入输出都结构化。

示例：

```json
{
  "step": "SearchWebNode",
  "input": {
    "queries": ["AI knowledge base agent product", "GraphRAG personal knowledge base"]
  },
  "output": {
    "sources": [
      {
        "title": "...",
        "url": "...",
        "snippet": "..."
      }
    ]
  }
}
```

---

# 11. 模型支持设计

## 11.1 模型任务分类

| 任务 | 模型类型 | 是否必须 |
|---|---|---|
| 文档摘要 | LLM | 必须 |
| 问答生成 | LLM | 必须 |
| 深度研究 | 高能力 LLM | 必须 |
| 实体识别 | LLM + 规则 + 词典 | 必须 |
| 关系抽取 | LLM | 必须 |
| 自动分类 | LLM / 分类模型 | 必须 |
| 实体类型自动发现 | Embedding + LLM | 必须 |
| 向量检索 | Embedding | 必须 |
| 重排序 | Reranker | 强烈建议 |
| OCR | OCR 模型 | 必须 |
| 图片理解 | 多模态模型 | 建议 |
| 股票代码识别 | 规则 + 词典 + LLM | 必须 |
| 产业链抽取 | LLM + 领域词典 | 必须 |

---

## 11.2 本地模型推荐

### 11.2.1 LLM

适合本地部署：

```text
Qwen 系列
Llama 系列
Gemma 系列
DeepSeek 系列蒸馏模型
GLM 系列开源模型
```

推荐用途：

| 模型用途 | 建议 |
|---|---|
| 普通摘要 | 本地 7B/8B/14B 模型 |
| 普通知识问答 | 本地 7B/14B 模型 |
| 实体抽取 | 本地 14B 以上效果更稳 |
| 关系抽取 | 本地 14B 以上或云模型 |
| 深度研究 | 云模型或本地大模型 |

### 11.2.2 Embedding

推荐：

```text
bge-m3
bge-large-zh
gte-multilingual
Qwen embedding
```

其中 bge-m3 适合多语言和中文场景。

### 11.2.3 Reranker

推荐：

```text
bge-reranker-v2-m3
jina-reranker
Qwen reranker
```

### 11.2.4 OCR

推荐：

```text
PaddleOCR
Tesseract
MinerU
Marker
```

中文、表格、PDF 场景优先考虑 PaddleOCR、MinerU、Marker。

---

## 11.3 云模型推荐

复杂任务建议支持云模型：

```text
OpenAI GPT 系列
Google Gemini 系列
Anthropic Claude 系列
智谱 GLM
通义千问
DeepSeek API
```

适合云模型的任务：

1. 深度研究。
2. 长文档归纳。
3. 高质量关系抽取。
4. 多网页交叉验证。
5. 报告生成。
6. NotebookLM 资料包问题生成。

---

## 11.4 模型路由策略

```text
任务进入
  ↓
判断敏感等级
  ↓
判断任务复杂度
  ↓
判断是否需要联网
  ↓
选择本地模型或云模型
  ↓
执行任务
  ↓
记录模型调用日志
```

路由规则示例：

| 场景 | 模型选择 |
|---|---|
| 私密文档摘要 | 本地 LLM |
| 普通 PDF 摘要 | 本地或低成本云模型 |
| 关系抽取低置信度复核 | 高能力云模型 |
| 深度研究 | 高能力云模型 |
| OCR | 本地 OCR |
| Embedding | 本地 embedding |
| Rerank | 本地 reranker |
| 股票最新数据解释 | 联网搜索 + 云模型总结 |

---

# 12. 模型调用抽象接口

后端需要定义统一模型接口，避免业务代码绑定某一个厂商。

```python
from typing import Protocol

class LLMClient(Protocol):
    async def chat(self, messages: list[dict], **kwargs) -> dict:
        ...

    async def structured_output(self, messages: list[dict], schema: dict, **kwargs) -> dict:
        ...

class EmbeddingClient(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_query(self, text: str) -> list[float]:
        ...

class RerankerClient(Protocol):
    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[dict]:
        ...

class OCRClient(Protocol):
    async def extract_text(self, file_path: str) -> dict:
        ...
```

业务层只调用抽象接口：

```python
result = await llm.structured_output(
    messages=messages,
    schema=EntityExtractionSchema.model_json_schema()
)
```

---

# 13. 后端模块划分

推荐目录：

```text
backend/
  app/
    api/
      v1/
        documents.py
        search.py
        chat.py
        entities.py
        graph.py
        research.py
        annotations.py
        notebooklm.py
        models.py
    core/
      config.py
      security.py
      logging.py
      task_queue.py
    domain/
      document/
      entity/
      graph/
      search/
      research/
      annotation/
      model/
    services/
      document_parser_service.py
      chunk_service.py
      embedding_service.py
      entity_extraction_service.py
      relation_extraction_service.py
      graph_sync_service.py
      hybrid_search_service.py
      rag_service.py
      research_agent_service.py
    infrastructure/
      db/
      vectorstore/
      graphstore/
      filestore/
      model_clients/
      web_search/
    workers/
      parse_worker.py
      embedding_worker.py
      entity_worker.py
      relation_worker.py
      research_worker.py
    schemas/
    tests/
```

---

# 14. 前端模块划分

推荐目录：

```text
frontend/
  src/
    pages/
      Dashboard/
      Library/
      Import/
      Reader/
      Graph/
      Search/
      Research/
      Entities/
      NotebookLM/
      Settings/
    components/
      DocumentList/
      CategoryTree/
      ReaderView/
      AnnotationPanel/
      GraphCanvas/
      EntityPanel/
      SearchBox/
      AgentProgress/
    services/
      documentApi.ts
      searchApi.ts
      entityApi.ts
      graphApi.ts
      researchApi.ts
    stores/
      workspaceStore.ts
      documentStore.ts
      graphStore.ts
    types/
```

---

# 15. 部署方式

## 15.1 单机个人版

```text
Tauri 桌面端
  ↓
内置启动 FastAPI
  ↓
SQLite
  ↓
Qdrant Local / Chroma / pgvector
  ↓
KuzuDB
  ↓
本地文件目录
  ↓
Ollama
```

适合：

- 个人用户。
- 轻量知识库。
- 隐私优先。

---

## 15.2 Docker Compose 专业版

```yaml
services:
  backend:
    image: knowpilot-backend
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - qdrant
      - redis
      - minio

  frontend:
    image: knowpilot-frontend
    ports:
      - "8080:80"

  postgres:
    image: postgres:16

  redis:
    image: redis:7

  qdrant:
    image: qdrant/qdrant

  minio:
    image: minio/minio

  nebula-metad:
    image: vesoft/nebula-metad

  nebula-storaged:
    image: vesoft/nebula-storaged

  nebula-graphd:
    image: vesoft/nebula-graphd
```

适合：

- 重度个人用户。
- 小团队。
- 大量文档。
- 图谱和向量数据较多。

---

# 16. 开发优先级建议

## 16.1 第一阶段：最小可用核心

1. FastAPI 后端骨架。
2. React 前端骨架。
3. SQLite/PostgreSQL 文档表。
4. 文件上传。
5. PDF/Word/Markdown/TXT 解析。
6. 文档列表和阅读。
7. 文档编辑和版本保存。
8. 全文搜索。

## 16.2 第二阶段：RAG 问答

1. Chunk 切分。
2. Embedding 生成。
3. Qdrant / pgvector 入库。
4. 语义搜索。
5. Reranker。
6. 带引用问答。

## 16.3 第三阶段：实体和图谱

1. entity_type / entity / relation 表。
2. LLM 实体抽取。
3. LLM 关系抽取。
4. 图数据库同步。
5. 图谱前端展示。
6. 节点扩展。

## 16.4 第四阶段：产业链和股票增强

1. 股票实体识别。
2. 股票代码词典。
3. 行业分类词典。
4. 产业链节点抽取。
5. 上下游关系抽取。
6. 公司-产品-客户-供应商图谱。

## 16.5 第五阶段：深度研究和 NotebookLM

1. 深度研究 Agent Workflow。
2. 网络搜索。
3. 研究报告生成。
4. 研究结果入库。
5. NotebookLM 资料包导出。
6. 企业版 API 对接。

---

# 17. 技术选型最终建议

## 17.1 MVP 推荐组合

```text
前端：React + TypeScript + Vite + Ant Design
桌面：先 Web，后 Tauri
后端：Python 3.12 + FastAPI + Pydantic v2
关系库：PostgreSQL，轻量版可 SQLite
全文搜索：PostgreSQL FTS，后续 OpenSearch
向量库：Qdrant
图数据库：KuzuDB 起步，专业版 NebulaGraph
文件存储：本地目录，专业版 MinIO
任务队列：Celery + Redis
模型服务：Ollama + 云模型 API
OCR：PaddleOCR + Marker/MinerU
Embedding：bge-m3 / Qwen embedding
Reranker：bge-reranker-v2-m3
Agent：LangGraph 或自研 Workflow
```

## 17.2 为什么这样选

1. Python/FastAPI 能最快接入 AI 能力。
2. React/TypeScript 能支撑复杂交互。
3. PostgreSQL 负责可靠业务数据。
4. Qdrant 负责专业向量检索。
5. KuzuDB/NebulaGraph 负责实体关系和路径查询。
6. MinIO/本地目录负责文件资产。
7. Ollama 负责本地模型，云模型负责复杂任务。
8. 模型路由保证隐私、成本和效果之间可平衡。

---

# 18. 最大技术风险

## 18.1 风险一：实体和关系抽取准确率不足

解决：

- 使用 JSON Schema 约束输出。
- 每条关系必须有 evidence。
- 低置信度人工审核。
- 支持用户修正。
- 修正结果进入 few-shot 示例库。

## 18.2 风险二：PDF 和表格解析质量不稳定

解决：

- 保存原始文件。
- 解析结果可编辑。
- 多解析器 fallback。
- 重要文档允许手动重新解析。

## 18.3 风险三：搜索结果不准

解决：

- 不只做向量检索。
- 使用 BM25 + 向量 + 图谱 + Reranker。
- Chunk 保留标题、页码、实体信息。
- 搜索结果支持用户反馈。

## 18.4 风险四：图谱太复杂

解决：

- 图谱按需展开。
- 默认只显示核心节点。
- 支持聚类和折叠。
- 支持关系置信度过滤。

## 18.5 风险五：本地部署过重

解决：

- 轻量版使用 SQLite + KuzuDB + 本地文件。
- 专业版再引入 PostgreSQL、Qdrant、NebulaGraph、MinIO。
- 所有组件模块化，可按需启用。

---

# 19. 架构结论

本项目最佳技术路线是：

> 用 Python/FastAPI 构建 AI 后端，用 React/TypeScript 构建复杂知识工作台，用 PostgreSQL/SQLite 存业务数据，用 Qdrant 做语义检索，用 KuzuDB/NebulaGraph 做知识图谱，用本地模型和云模型混合驱动 Agent 工作流。

这个架构的核心不是“堆技术组件”，而是明确每类数据的职责：

- 文档和用户操作记录进关系库。
- 原始文件进文件存储。
- 文档片段进向量库。
- 实体关系进图数据库。
- 搜索结果由全文、向量、图谱共同融合。
- AI 生成内容必须绑定来源和版本。

只要这条主线稳定，后续无论扩展股票研究、产业链图谱、NotebookLM 对接、浏览器插件，还是团队协作，都不会推倒重来。

