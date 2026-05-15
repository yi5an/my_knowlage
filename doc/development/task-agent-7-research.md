你是 KnowPilot 项目的深度研究 Agent 开发者。

你的目标：
实现结构化 Deep Research Workflow，而不是自由散漫的单轮问答。

请完成：
1. 创建 ResearchAgentService。
2. 创建研究任务接口：
   - POST /api/v1/research/tasks
   - GET /api/v1/research/tasks/{task_id}
   - GET /api/v1/research/tasks/{task_id}/progress
   - POST /api/v1/research/tasks/{task_id}/import
3. 实现固定 workflow：
   - PlanResearchNode
   - SearchLocalKnowledgeNode
   - SearchWebNode
   - ReadSourcesNode
   - ExtractClaimsNode
   - CrossCheckNode
   - GenerateReportNode
   - ImportToKnowledgeBaseNode
4. 每个节点输入输出必须结构化。
5. 支持本地知识库搜索。
6. 网络搜索先定义 WebSearchClient 抽象和 MockWebSearchClient。
7. 研究报告必须包含：
   - 摘要
   - 背景
   - 关键发现
   - 证据
   - 对比表
   - 风险与不确定性
   - 下一步建议
8. 研究来源写入 research_source。
9. 研究报告可以保存为 document。
10. 导入知识库时触发实体识别和关系抽取任务。
11. 添加测试：
   - 创建研究任务
   - mock 本地搜索
   - mock 网络搜索
   - 生成报告
   - 导入结果

边界：
- 不要实现真实联网搜索，先用抽象和 mock。
- 不要实现完整前端页面。
- 不要改动 RAG 搜索核心逻辑。
- 不要直接写死模型 Provider。

验收标准：
- 可以创建研究任务。
- 可以查看研究进度。
- 可以基于 mock sources 生成结构化报告。
- 可以把报告导入为 document。
- 每个 workflow step 都有状态记录。

分支名：
feat/deep-research-agent
