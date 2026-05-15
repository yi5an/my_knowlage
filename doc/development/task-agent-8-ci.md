你是 KnowPilot 项目的测试、CI 和文档 Agent。

你的目标：
建立研发质量保障体系，让其他 Agent 的代码可以被持续验证。

请完成：
1. 创建 GitHub Actions CI。
2. 后端 CI 包括：
   - 安装依赖
   - ruff check
   - mypy
   - pytest
3. 前端 CI 包括：
   - npm install
   - npm run lint
   - npm run test
   - npm run build
4. 创建测试数据目录：
   - tests/fixtures/documents
   - tests/fixtures/entities
   - tests/fixtures/research
5. 创建最小测试样本：
   - markdown 文档
   - txt 文档
   - 股票实体样本文本
   - 产业链样本文本
   - RAG 问答样本
6. 创建 docs/development/testing-guide.md。
7. 创建 docs/development/local-dev-guide.md。
8. 创建 docs/development/api-conventions.md。
9. 创建 docs/development/error-codes.md。
10. 检查 README 是否能指导新开发者启动项目。
11. 不要大量修改业务代码，只补测试和文档。
12. 如果发现业务代码明显无法测试，可以提出小型重构 PR。

边界：
- 不要实现主要业务功能。
- 不要重写其他 Agent 的模块。
- 不要引入复杂 CI 依赖。
- 不要使用真实 API Key。

验收标准：
- CI 文件存在。
- 本地测试指南完整。
- 有 fixtures。
- 有错误码文档。
- 后端和前端基础测试可运行。
- README 有清晰启动步骤。

分支名：
test/ci-and-quality
