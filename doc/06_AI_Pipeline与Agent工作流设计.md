# AI Pipeline 与 Agent 工作流设计

> 项目：KnowPilot AI Agent 本地知识库工具  
> 用途：指导产品、前端、后端、算法、测试和运维团队协同研发  
> 版本：v0.1  
> 日期：2026-05-15


## 1. 设计原则

1. 所有 AI 任务必须有输入、输出和状态。
2. 所有模型输出必须经过 JSON Schema 校验。
3. 所有 AI 结果必须绑定来源。
4. 高风险结果必须允许人工确认。
5. 深度研究使用受控 Workflow，不做完全自由 Agent。
6. 敏感文档默认走本地模型。

---

## 2. 文档解析 Pipeline

```text
文件输入
  ↓
文件类型识别
  ↓
原始文件保存
  ↓
文本提取 / OCR
  ↓
结构化 Markdown
  ↓
文档版本保存
  ↓
Chunk 切分
  ↓
摘要生成
  ↓
Embedding 生成
  ↓
全文索引
  ↓
实体识别
  ↓
关系抽取
  ↓
图谱同步
```

### 2.1 输入

```json
{
  "doc_id": "doc_001",
  "file_id": "file_001",
  "options": {
    "ocr_enabled": true,
    "extract_entities": true,
    "extract_relations": true
  }
}
```

### 2.2 输出

```json
{
  "doc_id": "doc_001",
  "version_id": "ver_001",
  "chunk_count": 86,
  "entity_count": 38,
  "relation_count": 72,
  "status": "completed"
}
```

### 2.3 失败处理

| 阶段 | 失败处理 |
|---|---|
| 文件读取 | 标记 parse_failed，提示文件损坏或格式不支持 |
| OCR | 保留原文件，允许关闭 OCR 重新解析 |
| Chunk | 记录错误，允许使用默认切分策略重试 |
| Embedding | 文档可用，但语义搜索不可用，稍后重试 |
| 实体识别 | 文档可用，实体状态 failed |
| 图谱同步 | 关系库成功，图数据库稍后重试 |

---

## 3. Chunk 切分 Pipeline

### 3.1 策略

| 文档类型 | 切分策略 |
|---|---|
| PDF | 页码 + 标题层级 |
| Word | 标题层级 |
| Excel | Sheet + 表格区域 |
| Markdown | 标题层级 |
| 代码 | 函数、类、配置段 |
| 图片 OCR | 按段落或版面区域 |

### 3.2 Chunk 元数据

```json
{
  "chunk_id": "chunk_001",
  "doc_id": "doc_001",
  "version_id": "ver_001",
  "heading": "实体识别设计",
  "page_no": 12,
  "content": "...",
  "token_count": 512,
  "metadata": {
    "section_path": ["技术架构", "实体识别"],
    "content_type": "paragraph"
  }
}
```

---

## 4. RAG Pipeline

```text
用户问题
  ↓
问题清洗
  ↓
问题改写
  ↓
问题实体识别
  ↓
关键词检索
  ↓
向量检索
  ↓
图谱扩展
  ↓
RRF 融合排序
  ↓
Reranker 重排序
  ↓
上下文压缩
  ↓
LLM 生成答案
  ↓
引用校验
  ↓
返回答案
```

### 4.1 检索融合

采用 RRF：

```text
score = keyword_score + vector_score + graph_score + annotation_score
```

再使用 Reranker 对 Top 50 重排，取 Top 8-12 构造上下文。

### 4.2 回答约束

1. 只能使用上下文回答。
2. 回答必须包含引用。
3. 无证据必须说明不足。
4. 对股票、政策、新闻类问题必须提示时效性。

---

## 5. 实体识别 Pipeline

```text
Chunk 输入
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
重复合并建议
  ↓
写入 entity_mention
  ↓
写入或更新 entity
```

### 5.1 规则识别

- IP 地址
- 端口
- 文件路径
- 配置项
- 股票代码
- URL
- 日期
- 金额
- 百分比

### 5.2 词典识别

词典包括：

- 公司词典
- 股票代码词典
- 行业分类词典
- 财务指标词典
- 技术名词词典
- 产业链环节词典

### 5.3 LLM 抽取

要求：

1. 输出 JSON。
2. 每个实体必须有 evidence。
3. 每个实体必须有 confidence。
4. 未知类型可输出 `candidate_type`。

---

## 6. 实体类型自动丰富 Pipeline

```text
未归类名词短语池
  ↓
频次统计
  ↓
跨文档出现过滤
  ↓
Embedding 聚类
  ↓
与已有实体类型比对
  ↓
LLM 归纳上位类型
  ↓
生成 entity_type 建议
  ↓
用户确认
  ↓
写入实体类型库
```

### 6.1 触发条件

| 条件 | 建议阈值 |
|---|---:|
| 候选实体数量 | >= 5 |
| 跨文档出现数量 | >= 3 |
| 聚类相似度 | >= 0.75 |
| LLM 置信度 | >= 0.80 |
| 用户确认 | 必须 |

---

## 7. 关系抽取 Pipeline

```text
Chunk
  ↓
获取 Chunk 内实体
  ↓
构造候选实体对
  ↓
过滤不可能关系
  ↓
LLM 判断关系
  ↓
Schema 校验
  ↓
关系标准化
  ↓
证据绑定
  ↓
写入 entity_relation
  ↓
同步图数据库
```

### 7.1 候选实体对过滤

规则：

1. 同一 Chunk 内共现优先。
2. 标题实体与段落实体可构成候选对。
3. 不同类型之间按 relation_type 约束。
4. 距离过远的实体默认不构造关系。

### 7.2 输出要求

```json
{
  "relations": [
    {
      "source_entity": "英伟达",
      "target_entity": "台积电",
      "relation_type": "依赖",
      "evidence_text": "英伟达的高端 GPU 主要依赖台积电先进制程代工。",
      "confidence": 0.88
    }
  ]
}
```

---

## 8. 图谱同步 Pipeline

```text
entity / relation 变更
  ↓
outbox_event
  ↓
graph_sync_worker
  ↓
写入 KuzuDB / NebulaGraph
  ↓
更新同步状态
```

失败处理：

1. 图谱同步失败不影响主业务数据。
2. 失败事件进入重试队列。
3. 支持按 workspace 全量重建图谱。

---

## 9. 深度研究 Agent Workflow

MVP 不做完全自由 Agent，采用固定节点：

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

### 9.1 PlanResearchNode

输入：用户问题。  
输出：研究计划、子问题、搜索关键词。

### 9.2 SearchLocalKnowledgeNode

输入：子问题和关键词。  
输出：本地文档、Chunk、实体、标注。

### 9.3 SearchWebNode

输入：搜索关键词。  
输出：网页标题、URL、摘要、可信度初评。

### 9.4 ReadSourcesNode

输入：来源列表。  
输出：来源摘要、关键观点、可引用证据。

### 9.5 ExtractClaimsNode

输入：来源摘要。  
输出：观点、事实、数据、风险、不确定性。

### 9.6 CrossCheckNode

输入：多来源观点。  
输出：一致观点、冲突观点、证据强度。

### 9.7 GenerateReportNode

输入：研究材料。  
输出：结构化研究报告。

### 9.8 ImportToKnowledgeBaseNode

输入：研究报告。  
输出：文档、实体、关系、来源记录。

---

## 10. 模型路由

```text
任务输入
  ↓
判断文档敏感等级
  ↓
判断任务复杂度
  ↓
判断是否需要联网
  ↓
选择模型
  ↓
执行
  ↓
记录日志
```

| 任务 | 默认模型 |
|---|---|
| OCR | PaddleOCR / MinerU |
| Embedding | bge-m3 / Qwen embedding |
| Rerank | bge-reranker |
| 普通摘要 | 本地 LLM |
| 复杂关系抽取 | 云模型或高能力本地模型 |
| 深度研究 | 高能力云模型优先 |
| 敏感文档 | 本地模型 |

---

## 11. 质量控制

1. 每个 AI Pipeline 节点都要保存输入输出。
2. 失败可重试。
3. 输出 Schema 校验失败自动重试一次。
4. 重试失败进入人工处理。
5. 用户修改结果进入反馈样本库。
6. Prompt 必须版本化。
