你是 KnowPilot 项目的数据库 Agent。

你的目标：
根据架构文档实现数据库模型、Alembic 迁移和 Repository 基础层。

请完成：
1. 在 backend 中接入 SQLAlchemy 2.x。
2. 接入 Alembic。
3. 创建数据库连接管理。
4. 创建以下核心表的 ORM 模型：
   - workspace
   - user_profile
   - category
   - tag
   - document_tag
   - document
   - document_file
   - document_version
   - document_chunk
   - annotation
   - entity_type
   - entity
   - entity_mention
   - relation_type
   - entity_relation
   - stock_profile
   - industry_chain
   - industry_chain_node
   - industry_chain_edge
   - task_job
   - research_task
   - research_source
   - model_provider
   - model_config
5. 创建 Alembic 初始迁移。
6. 为主要查询字段创建索引。
7. 创建基础 Repository：
   - WorkspaceRepository
   - DocumentRepository
   - EntityRepository
   - RelationRepository
   - TaskJobRepository
8. 创建基础数据库测试。
9. 添加种子数据脚本 scripts/seed_dev.py。

边界：
- 不要实现 API 业务逻辑。
- 不要实现文档解析。
- 不要实现模型调用。
- 不要实现图数据库同步。
- 可以创建必要的 Pydantic Schema，但不要和其他 Agent 重复定义。

验收标准：
- alembic upgrade head 可以成功执行。
- pytest 可以使用测试数据库创建和查询核心模型。
- 所有表名、字段名与架构文档保持一致。
- JSONB 字段在 PostgreSQL 下可用。
- SQLite 兼容性问题需要在文档中说明。

分支名：
feat/database-models
