# API 接口详细设计文档

> 项目：KnowPilot AI Agent 本地知识库工具  
> 用途：指导产品、前端、后端、算法、测试和运维团队协同研发  
> 版本：v0.1  
> 日期：2026-05-15


## 1. 接口约定

基础路径：

```http
/api/v1
```

通用响应：

```json
{{
  "success": true,
  "data": {{}},
  "error": null,
  "trace_id": "req_001"
}}
```

通用错误响应：

```json
{{
  "success": false,
  "data": null,
  "error": {{
    "code": "VALIDATION_ERROR",
    "message": "参数错误",
    "details": {{}}
  }},
  "trace_id": "req_001"
}}
```

## 2. 错误码

| 错误码 | 说明 |
|---|---|
| VALIDATION_ERROR | 参数错误 |
| NOT_FOUND | 数据不存在 |
| FILE_TOO_LARGE | 文件过大 |
| UNSUPPORTED_FILE_TYPE | 文件格式不支持 |
| DUPLICATED_FILE | 文件已存在 |
| PARSE_FAILED | 解析失败 |
| OCR_FAILED | OCR 失败 |
| MODEL_NOT_CONFIGURED | 模型未配置 |
| MODEL_CALL_FAILED | 模型调用失败 |
| VECTOR_INDEX_FAILED | 向量索引失败 |
| GRAPH_SYNC_FAILED | 图谱同步失败 |
| PERMISSION_DENIED | 权限不足 |

---

## 3. 文档导入接口

### 3.1 上传文件

```http
POST /api/v1/documents/import/file
Content-Type: multipart/form-data
```

请求参数：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| file | File | 是 | 上传文件 |
| workspace_id | string | 是 | 工作空间 ID |
| category_id | string | 否 | 分类 ID |
| auto_parse | boolean | 否 | 是否自动解析，默认 true |
| ocr_enabled | boolean | 否 | 是否开启 OCR，默认 true |
| extract_entities | boolean | 否 | 是否抽取实体，默认 true |
| extract_relations | boolean | 否 | 是否抽取关系，默认 true |

响应：

```json
{{
  "success": true,
  "data": {{
    "doc_id": "doc_001",
    "file_id": "file_001",
    "job_id": "job_001",
    "status": "pending"
  }}
}}
```

触发表：`document_file`、`document`、`task_job`。

### 3.2 URL 导入

```http
POST /api/v1/documents/import/url
```

请求：

```json
{{
  "workspace_id": "ws_001",
  "url": "https://example.com/article",
  "category_id": "cat_001",
  "options": {{
    "save_snapshot": true,
    "auto_parse": true,
    "extract_entities": true,
    "extract_relations": true
  }}
}}
```

响应：

```json
{{
  "success": true,
  "data": {{
    "doc_id": "doc_002",
    "job_id": "job_002",
    "status": "pending"
  }}
}}
```

---

## 4. 文档管理接口

### 4.1 文档列表

```http
GET /api/v1/documents
```

查询参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| workspace_id | string | 工作空间 |
| category_id | string | 分类 |
| tag_id | string | 标签 |
| source_type | string | 来源类型 |
| keyword | string | 搜索关键词 |
| status | string | 文档状态 |
| page | int | 页码 |
| page_size | int | 每页条数 |

响应：

```json
{{
  "success": true,
  "data": {{
    "items": [
      {{
        "id": "doc_001",
        "title": "AI Agent 本地知识库 PRD",
        "summary": "...",
        "category_path": "技术/AI/Agent",
        "tags": ["RAG", "图谱"],
        "parse_status": "completed",
        "entity_count": 38,
        "relation_count": 72,
        "updated_at": "2026-05-15T10:00:00Z"
      }}
    ],
    "total": 1
  }}
}}
```

### 4.2 文档详情

```http
GET /api/v1/documents/{{doc_id}}
```

### 4.3 文档版本内容

```http
GET /api/v1/documents/{{doc_id}}/versions/{{version_id}}
```

### 4.4 保存文档内容

```http
PUT /api/v1/documents/{{doc_id}}/content
```

请求：

```json
{{
  "base_version_id": "ver_001",
  "title": "AI Agent 本地知识库 PRD",
  "content_md": "# 正文...",
  "change_summary": "修改实体识别章节",
  "reindex": true,
  "rerun_entity_extraction": false
}}
```

响应：

```json
{{
  "success": true,
  "data": {{
    "doc_id": "doc_001",
    "version_id": "ver_002",
    "reindex_job_id": "job_102"
  }}
}}
```

---

## 5. 标注接口

### 5.1 创建标注

```http
POST /api/v1/annotations
```

请求：

```json
{{
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
}}
```

### 5.2 查询文档标注

```http
GET /api/v1/documents/{{doc_id}}/annotations
```

### 5.3 修改标注

```http
PUT /api/v1/annotations/{{annotation_id}}
```

### 5.4 删除标注

```http
DELETE /api/v1/annotations/{{annotation_id}}
```

---

## 6. 搜索与问答接口

### 6.1 混合搜索

```http
POST /api/v1/search
```

请求：

```json
{{
  "workspace_id": "ws_001",
  "query": "GraphRAG 在本地知识库中的作用",
  "search_types": ["keyword", "vector", "graph", "annotation"],
  "filters": {{
    "category_ids": ["cat_ai"],
    "entity_types": ["技术", "产品"],
    "source_types": ["pdf", "url"]
  }},
  "top_k": 20,
  "rerank": true
}}
```

响应：

```json
{{
  "success": true,
  "data": {{
    "results": [
      {{
        "doc_id": "doc_001",
        "chunk_id": "chunk_009",
        "title": "AI Agent 本地知识库 PRD",
        "snippet": "GraphRAG 是核心技术路线之一...",
        "score": 0.92,
        "source_type": "vector",
        "entities": ["GraphRAG", "RAG", "图数据库"]
      }}
    ]
  }}
}}
```

### 6.2 RAG 问答

```http
POST /api/v1/chat/query
```

请求：

```json
{{
  "workspace_id": "ws_001",
  "question": "我的知识库中 GraphRAG 主要和哪些技术相关？",
  "scope": {{
    "category_ids": ["cat_ai"],
    "doc_ids": []
  }},
  "answer_mode": "grounded",
  "include_graph_context": true
}}
```

响应：

```json
{{
  "success": true,
  "data": {{
    "answer": "GraphRAG 主要和 RAG、向量数据库、图数据库、实体关系抽取相关...",
    "citations": [
      {{
        "doc_id": "doc_001",
        "chunk_id": "chunk_009",
        "text": "GraphRAG 是核心技术路线之一..."
      }}
    ],
    "related_entities": ["GraphRAG", "RAG", "Qdrant", "NebulaGraph"]
  }}
}}
```

---

## 7. 实体接口

### 7.1 实体列表

```http
GET /api/v1/entities?workspace_id=ws_001&type=股票/证券&keyword=英伟达
```

### 7.2 实体详情

```http
GET /api/v1/entities/{{entity_id}}
```

### 7.3 修改实体

```http
PUT /api/v1/entities/{{entity_id}}
```

请求：

```json
{{
  "name": "英伟达",
  "entity_type": "股票/证券",
  "aliases": ["NVIDIA", "NVDA"],
  "properties": {{
    "ticker": "NVDA",
    "exchange": "NASDAQ",
    "industry": "半导体",
    "sector": "AI 芯片"
  }},
  "verified": true
}}
```

### 7.4 合并实体

```http
POST /api/v1/entities/merge
```

请求：

```json
{{
  "workspace_id": "ws_001",
  "target_entity_id": "entity_nvda",
  "source_entity_ids": ["entity_nvidia", "entity_yingweida"],
  "merge_aliases": true,
  "merge_relations": true
}}
```

### 7.5 自动发现实体类型

```http
POST /api/v1/entity-types/discover
```

### 7.6 确认新增实体类型

```http
POST /api/v1/entity-types
```

---

## 8. 图谱接口

### 8.1 查询节点邻居

```http
GET /api/v1/graph/entities/{{entity_id}}/neighbors?depth=1&limit=50
```

### 8.2 图谱搜索

```http
POST /api/v1/graph/search
```

### 8.3 路径查询

```http
POST /api/v1/graph/path
```

### 8.4 查询关系证据

```http
GET /api/v1/graph/relations/{{relation_id}}/evidence
```

---

## 9. 深度研究接口

### 9.1 创建研究任务

```http
POST /api/v1/research/tasks
```

### 9.2 获取研究进度

```http
GET /api/v1/research/tasks/{{task_id}}/progress
```

### 9.3 获取研究报告

```http
GET /api/v1/research/tasks/{{task_id}}/report
```

### 9.4 导入研究结果

```http
POST /api/v1/research/tasks/{{task_id}}/import
```

---

## 10. 模型接口

### 10.1 模型列表

```http
GET /api/v1/models
```

### 10.2 新增模型 Provider

```http
POST /api/v1/model-providers
```

### 10.3 测试模型

```http
POST /api/v1/models/test
```

### 10.4 配置模型路由

```http
PUT /api/v1/model-routing
```

---

## 11. 任务接口

### 11.1 查询任务详情

```http
GET /api/v1/tasks/{{job_id}}
```

### 11.2 任务事件流

```http
GET /api/v1/tasks/{{job_id}}/events
```

建议使用 SSE 返回任务进度。

### 11.3 重试任务

```http
POST /api/v1/tasks/{{job_id}}/retry
```

---

## 12. NotebookLM 接口

### 12.1 生成资料包

```http
POST /api/v1/notebooklm/export-package
```

### 12.2 查看导出历史

```http
GET /api/v1/notebooklm/exports
```

---

## 13. 接口实现约束

1. 所有写接口必须记录 updated_at。
2. 所有异步任务接口必须返回 job_id。
3. 所有模型相关接口必须记录调用日志。
4. 所有 AI 生成内容必须保存模型名称、prompt_version、source_refs。
5. 所有删除操作 MVP 优先软删除。
