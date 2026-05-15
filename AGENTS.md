# AGENTS.md

## Project

This repository is for KnowPilot, an AI Agent powered local-first knowledge base.

The product supports:
- Multi-format document import
- Document parsing and editing
- Entity extraction
- Relation extraction
- Knowledge graph
- Hybrid search
- RAG Q&A
- Deep research
- NotebookLM export package

## Architecture

Backend:
- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- Celery or Dramatiq
- PostgreSQL first, SQLite-compatible where possible

Frontend:
- React
- TypeScript
- Vite
- Ant Design or shadcn/ui
- TanStack Query
- Zustand

Storage:
- PostgreSQL for business data
- Qdrant for vector search
- KuzuDB or NebulaGraph adapter for graph data
- Local file storage first
- MinIO-compatible abstraction for later

AI:
- Model provider abstraction
- Embedding client abstraction
- Reranker client abstraction
- LLM structured output with JSON Schema
- OCR abstraction

## Coding Rules

1. Use schema-driven development.
2. Define Pydantic schemas before implementing service logic.
3. Keep API, service, domain, and infrastructure layers separated.
4. Do not hardcode model providers.
5. Do not hardcode file storage paths outside config.
6. Every AI-generated result must support evidence and confidence fields.
7. Entity and relation extraction must use structured JSON output.
8. Long-running jobs must be asynchronous and tracked in task_job.
9. Avoid circular imports.
10. Add tests for every new module.
11. Keep functions small and typed.
12. Prefer explicit error handling over silent fallback.
13. Never commit secrets or API keys.
14. Update README or module docs when adding major features.

## Backend Structure

backend/
  app/
    api/
      v1/
    core/
    domain/
    services/
    infrastructure/
    workers/
    schemas/
    tests/

## Frontend Structure

frontend/
  src/
    pages/
    components/
    services/
    stores/
    types/

## Testing Commands

Backend:
```bash
cd backend
pytest
ruff check .
mypy app
```

Frontend:
```bash
cd frontend
npm install
npm run lint
npm run test
npm run build
```
## Git Rules
Each Codex task should work on a focused branch.

Branch naming:

feat/project-bootstrap
feat/database-models
feat/document-import
feat/rag-search
feat/entity-extraction
feat/graph-service
feat/frontend-shell
feat/research-agent
test/ci-and-quality

Each PR must include:

Summary
Changed files
Test results
Known limitations
Follow-up tasks

---

# 三、主控 Agent 提示词

这个 Agent 不直接大量写业务代码，主要负责拆任务、检查接口一致性、避免并行冲突。

```text
你是 KnowPilot 项目的主控架构 Agent。

项目目标：
开发一个 AI Agent 驱动的本地知识库工具，支持文档导入、解析、编辑、实体识别、关系抽取、知识图谱、混合搜索、RAG 问答、深度研究和 NotebookLM 资料包导出。

你需要先阅读仓库中的所有产品、架构、API、数据库、AI Pipeline、Prompt、前端交互和测试文档。

你的任务：
1. 检查当前仓库结构是否适合多 Agent 并行开发。
2. 创建或完善 AGENTS.md。
3. 创建开发任务总览文档 docs/development/parallel-agent-plan.md。
4. 把项目拆成多个互不冲突的开发任务。
5. 明确每个 Agent 可以修改的目录范围。
6. 明确公共接口、公共 Schema、公共类型由哪个 Agent 负责。
7. 明确哪些文件禁止多个 Agent 同时修改。
8. 输出合并顺序和 PR 审查规则。
9. 不要一次性实现所有业务功能。
10. 只做项目规划、规范、骨架检查和任务边界定义。

并行 Agent 建议：
- Agent 0：项目骨架与工程规范
- Agent 1：数据库模型与迁移
- Agent 2：文档导入与解析
- Agent 3：向量检索与 RAG
- Agent 4：实体识别与关系抽取
- Agent 5：图谱服务
- Agent 6：前端 UI 框架与页面
- Agent 7：深度研究 Agent
- Agent 8：测试、CI、文档

输出要求：
- 给出最终建议的目录结构。
- 给出每个 Agent 的任务边界。
- 给出每个 Agent 的验收标准。
- 给出每个 Agent 的建议分支名。
- 给出 PR 合并顺序。
- 给出哪些接口或 Schema 必须先冻结。
- 给出冲突风险和规避策略。

完成后请运行可用的 lint/test 命令，如果仓库还没有测试框架，请说明原因并创建最小测试骨架。


# 四、Agent 0：项目骨架与工程规范
你是 KnowPilot 项目的工程骨架 Agent。

你的目标：
搭建项目基础工程结构，使其他 Agent 可以并行开发。

请完成：
1. 创建 backend/ 和 frontend/ 基础目录。
2. backend 使用 Python 3.12 + FastAPI + Pydantic v2。
3. 创建基础 FastAPI app。
4. 创建 app/core/config.py，使用 pydantic-settings 管理配置。
5. 创建 app/core/logging.py。
6. 创建 app/core/errors.py，定义统一异常结构。
7. 创建 app/api/v1/router.py。
8. 创建健康检查接口 GET /api/v1/health。
9. 创建 pyproject.toml，配置 pytest、ruff、mypy。
10. 创建 backend/tests/test_health.py。
11. frontend 使用 React + TypeScript + Vite。
12. 创建基础页面布局和路由，但不要实现复杂页面。
13. 创建 README.md，说明启动方式。
14. 创建 .env.example。
15. 创建 docker-compose.dev.yml 的基础版本，先包含 backend、frontend、postgres、redis。

边界：
- 不要实现文档导入业务。
- 不要实现数据库复杂模型。
- 不要实现 AI 模型调用。
- 不要实现图谱和 RAG。
- 只做基础工程骨架。

验收标准：
- backend 可以启动。
- GET /api/v1/health 返回 ok。
- pytest 可以运行。
- ruff check 可以运行。
- frontend 可以 npm run build。
- README 中有本地启动步骤。

分支名：
feat/project-bootstrap

