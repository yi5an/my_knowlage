# Prompt 模板与 JSON Schema 设计

> 项目：KnowPilot AI Agent 本地知识库工具  
> 用途：指导产品、前端、后端、算法、测试和运维团队协同研发  
> 版本：v0.1  
> 日期：2026-05-15


## 1. 设计原则

1. 不允许业务代码直接使用散落 Prompt。
2. Prompt 必须版本化。
3. 所有结构化任务必须使用 JSON Schema。
4. 所有输出必须带 evidence 和 confidence。
5. 允许模型说“不确定”。
6. 不允许模型凭常识补充原文没有的关系。

---

## 2. Prompt 版本管理

建议表：`prompt_template`

```sql
CREATE TABLE prompt_template (
  id VARCHAR(64) PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  version VARCHAR(32) NOT NULL,
  task_type VARCHAR(64) NOT NULL,
  content TEXT NOT NULL,
  output_schema JSONB,
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(name, version)
);
```

---

## 3. 文档摘要 Prompt

### 3.1 System Prompt

```text
你是一个严谨的知识库文档分析助手。你的任务是基于给定文档内容生成摘要。
要求：
1. 只能基于输入内容总结。
2. 不要添加输入中没有的信息。
3. 输出结构化 JSON。
4. 如果内容不足，明确说明。
```

### 3.2 User Prompt

```text
请分析以下文档内容，并生成摘要、关键词、适合分类和需要关注的问题。

文档标题：{{title}}
文档内容：
{{content}}
```

### 3.3 JSON Schema

```json
{
  "type": "object",
  "properties": {
    "summary": {"type": "string"},
    "key_points": {"type": "array", "items": {"type": "string"}},
    "keywords": {"type": "array", "items": {"type": "string"}},
    "suggested_category": {"type": "string"},
    "questions": {"type": "array", "items": {"type": "string"}},
    "confidence": {"type": "number"}
  },
  "required": ["summary", "key_points", "keywords", "confidence"]
}
```

---

## 4. 自动分类 Prompt

```text
你是知识库分类助手。请根据用户已有分类树和文档内容，为文档推荐最多 3 个候选分类。
规则：
1. 分类最多 3 级。
2. 优先选择已有分类。
3. 如果没有合适分类，可以建议新分类。
4. 必须给出理由和置信度。

已有分类树：
{{category_tree}}

文档标题：{{title}}
文档摘要：{{summary}}
关键词：{{keywords}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "category_path": {"type": "string"},
          "is_new": {"type": "boolean"},
          "reason": {"type": "string"},
          "confidence": {"type": "number"}
        },
        "required": ["category_path", "reason", "confidence"]
      }
    }
  },
  "required": ["candidates"]
}
```

---

## 5. 通用实体识别 Prompt

```text
你是实体识别助手。请从文本中抽取实体。

要求：
1. 只能抽取文本中明确出现或明确指代的实体。
2. 每个实体必须给出 evidence。
3. 每个实体必须给出类型、置信度。
4. 如果实体类型不在给定列表中，可输出 candidate_type。
5. 不要抽取过于泛化的普通词。

支持的实体类型：
{{entity_types}}

文本：
{{chunk_text}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "type": {"type": "string"},
          "candidate_type": {"type": "string"},
          "aliases": {"type": "array", "items": {"type": "string"}},
          "properties": {"type": "object"},
          "evidence": {"type": "string"},
          "confidence": {"type": "number"}
        },
        "required": ["name", "type", "evidence", "confidence"]
      }
    }
  },
  "required": ["entities"]
}
```

---

## 6. 股票实体识别 Prompt

```text
你是投资研究领域的实体识别助手。请识别文本中的股票/证券实体。

要求：
1. 识别公司全称、简称、股票代码、交易所。
2. 如果文本没有明确股票代码，不要凭空补充。
3. 可以识别行业、细分赛道、核心产品。
4. 每个字段都应尽量有证据。

文本：
{{chunk_text}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "stocks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "company_name": {"type": "string"},
          "company_short_name": {"type": "string"},
          "ticker": {"type": "string"},
          "exchange": {"type": "string"},
          "currency": {"type": "string"},
          "industry": {"type": "string"},
          "sector": {"type": "string"},
          "products": {"type": "array", "items": {"type": "string"}},
          "evidence": {"type": "string"},
          "confidence": {"type": "number"}
        },
        "required": ["company_name", "evidence", "confidence"]
      }
    }
  },
  "required": ["stocks"]
}
```

---

## 7. 产业链抽取 Prompt

```text
你是产业研究分析助手。请从文本中抽取产业链结构。

要求：
1. 识别产业链名称。
2. 识别上游、中游、下游环节。
3. 识别核心公司、关键产品、原材料、风险和政策因素。
4. 只基于文本证据，不要过度补充常识。

文本：
{{chunk_text}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "industry_chains": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "upstream": {"type": "array", "items": {"type": "string"}},
          "midstream": {"type": "array", "items": {"type": "string"}},
          "downstream": {"type": "array", "items": {"type": "string"}},
          "core_companies": {"type": "array", "items": {"type": "string"}},
          "key_products": {"type": "array", "items": {"type": "string"}},
          "risk_factors": {"type": "array", "items": {"type": "string"}},
          "policy_factors": {"type": "array", "items": {"type": "string"}},
          "evidence": {"type": "string"},
          "confidence": {"type": "number"}
        },
        "required": ["name", "evidence", "confidence"]
      }
    }
  },
  "required": ["industry_chains"]
}
```

---

## 8. 关系抽取 Prompt

```text
你是关系抽取助手。请根据文本和已识别实体，判断实体之间是否存在明确关系。

要求：
1. 只能基于原文证据判断关系。
2. 不要根据常识补充关系。
3. 每条关系必须包含 evidence_text。
4. 不确定则不要输出关系。
5. 关系类型必须从给定列表中选择。

关系类型：{{relation_types}}

实体列表：{{entities}}

文本：
{{chunk_text}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "relations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source_entity": {"type": "string"},
          "target_entity": {"type": "string"},
          "relation_type": {"type": "string"},
          "evidence_text": {"type": "string"},
          "confidence": {"type": "number"}
        },
        "required": ["source_entity", "target_entity", "relation_type", "evidence_text", "confidence"]
      }
    }
  },
  "required": ["relations"]
}
```

---

## 9. 实体类型自动发现 Prompt

```text
你是知识体系设计助手。下面是一组系统尚未归类的高频候选实体，请判断它们是否属于同一个上位实体类型。

要求：
1. 如果不属于同一类，返回 should_create=false。
2. 如果属于同一类，给出类型名称、定义、示例、识别规则。
3. 类型名称要简洁，适合成为知识库实体类型。

候选实体：
{{candidate_terms}}

已有实体类型：
{{existing_entity_types}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "should_create": {"type": "boolean"},
    "name": {"type": "string"},
    "domain": {"type": "string"},
    "description": {"type": "string"},
    "examples": {"type": "array", "items": {"type": "string"}},
    "rules": {"type": "array", "items": {"type": "string"}},
    "reason": {"type": "string"},
    "confidence": {"type": "number"}
  },
  "required": ["should_create", "reason", "confidence"]
}
```

---

## 10. RAG 回答 Prompt

```text
你是本地知识库问答助手。请基于给定上下文回答用户问题。

严格规则：
1. 只能使用上下文中的信息。
2. 每个关键结论后必须给出引用编号。
3. 如果上下文不足，直接说明不足。
4. 不要编造来源。
5. 股票、政策、新闻类内容需要提示资料日期。

用户问题：{{question}}

上下文：
{{contexts}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "answer": {"type": "string"},
    "citations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "ref_id": {"type": "string"},
          "doc_id": {"type": "string"},
          "chunk_id": {"type": "string"},
          "quote": {"type": "string"}
        },
        "required": ["ref_id", "doc_id", "chunk_id"]
      }
    },
    "not_enough_evidence": {"type": "boolean"},
    "followup_questions": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["answer", "citations", "not_enough_evidence"]
}
```

---

## 11. 深度研究计划 Prompt

```text
你是研究计划 Agent。请把用户问题拆解成可执行的研究计划。

要求：
1. 输出子问题。
2. 输出本地搜索关键词。
3. 输出网络搜索关键词。
4. 标记需要验证的风险点。
5. 不要直接写最终结论。

用户问题：{{question}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "research_goal": {"type": "string"},
    "sub_questions": {"type": "array", "items": {"type": "string"}},
    "local_search_queries": {"type": "array", "items": {"type": "string"}},
    "web_search_queries": {"type": "array", "items": {"type": "string"}},
    "risk_points": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["research_goal", "sub_questions", "local_search_queries"]
}
```

---

## 12. 深度研究报告 Prompt

```text
你是研究报告写作助手。请基于已验证的来源和观点生成研究报告。

要求：
1. 每个关键结论必须给出来源。
2. 区分事实、观点和推测。
3. 标记冲突观点和不确定性。
4. 给出下一步建议。

研究问题：{{question}}
来源材料：{{sources}}
观点抽取：{{claims}}
```

Schema：

```json
{
  "type": "object",
  "properties": {
    "title": {"type": "string"},
    "executive_summary": {"type": "string"},
    "key_findings": {"type": "array", "items": {"type": "string"}},
    "evidence_table": {"type": "array", "items": {"type": "object"}},
    "conflicts": {"type": "array", "items": {"type": "string"}},
    "uncertainties": {"type": "array", "items": {"type": "string"}},
    "recommendations": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["title", "executive_summary", "key_findings"]
}
```

---

## 13. Prompt 质量要求

1. Prompt 修改必须提升版本号。
2. Prompt 输出 Schema 失败率应纳入监控。
3. 高风险任务需要保存原始模型输出。
4. 用户修正结果应作为后续 few-shot 示例来源。
5. 不同模型可以配置不同 Prompt 版本。
