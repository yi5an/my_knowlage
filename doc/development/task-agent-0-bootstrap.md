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
