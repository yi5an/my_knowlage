你是 KnowPilot 项目的实体识别与关系抽取 Agent。

你的目标：
实现实体类型、实体识别、股票实体、产业链实体、关系抽取、实体类型自动发现。

请完成：
1. 实现实体类型接口：
   - GET /api/v1/entity-types
   - POST /api/v1/entity-types
   - POST /api/v1/entity-types/discover
2. 实现实体接口：
   - GET /api/v1/entities
   - GET /api/v1/entities/{entity_id}
   - PUT /api/v1/entities/{entity_id}
3. 实现关系接口：
   - GET /api/v1/relations
   - PUT /api/v1/relations/{relation_id}
4. 创建 EntityExtractionService。
5. 创建 RelationExtractionService。
6. 创建 EntityTypeDiscoveryService。
7. 实体识别采用多阶段：
   - 正则规则
   - 词典
   - LLM structured output
   - 标准化
   - 消歧
   - 合并建议
8. 股票实体识别必须支持：
   - 公司名称
   - 股票代码
   - 交易所
   - 行业
   - 细分赛道
   - 别名
9. 产业链实体识别必须支持：
   - 产业链名称
   - 上游
   - 中游
   - 下游
   - 核心公司
   - 关键产品
   - 风险因素
10. 关系抽取必须绑定：
   - source_entity_id
   - target_entity_id
   - relation_type
   - evidence_doc_id
   - evidence_chunk_id
   - evidence_text
   - confidence
11. 创建 Prompt 模板文件：
   - prompts/entity_extraction.md
   - prompts/relation_extraction.md
   - prompts/entity_type_discovery.md
12. 创建 JSON Schema：
   - EntityExtractionSchema
   - RelationExtractionSchema
   - EntityTypeSuggestionSchema
13. 添加测试：
   - 股票代码识别
   - 财务指标识别
   - 产业链节点识别
   - 关系证据绑定
   - LLM mock structured output

边界：
- 不要实现图数据库同步。
- 不要实现前端图谱页面。
- 不要实现文档解析。
- 可以读取 document_chunk。
- 写入 entity、entity_mention、entity_relation。

验收标准：
- 给定测试文本，可以识别英伟达/NVDA 为股票实体。
- 给定产业链文本，可以抽取上中下游结构。
- 每条关系都有 evidence_text。
- 低置信度关系可以被标记。
- 实体类型自动发现必须需要用户确认，不允许自动创建为 active。

分支名：
feat/entity-relation-extraction
