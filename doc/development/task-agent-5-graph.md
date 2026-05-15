你是 KnowPilot 项目的图谱服务 Agent。

你的目标：
实现图数据库适配层、图谱同步、邻居查询、路径查询和图谱搜索接口。

请完成：
1. 创建 GraphStore 抽象接口。
2. 实现 InMemoryGraphStore 用于测试。
3. 实现 KuzuGraphStore 或 NebulaGraphStore 的基础适配器。
4. 实现 GraphSyncService。
5. 从关系库同步以下数据到图数据库：
   - Document
   - Chunk
   - Entity
   - EntityType
   - entity_relation
   - entity_mention
6. 实现图谱接口：
   - GET /api/v1/graph/entities/{entity_id}/neighbors
   - POST /api/v1/graph/search
   - POST /api/v1/graph/path
7. 邻居查询支持：
   - depth
   - limit
   - node_types
   - relation_types
   - min_confidence
8. 路径查询支持：
   - source_entity_id
   - target_entity_id
   - max_depth
9. 返回前端图谱结构：
   - nodes
   - edges
   - node_type
   - relation_type
   - confidence
   - evidence
10. 添加测试：
   - 图同步
   - 一跳邻居查询
   - 二跳查询
   - 路径查询
   - 置信度过滤

边界：
- 不要实现实体抽取。
- 不要实现关系抽取。
- 不要实现前端图谱画布。
- 图数据库是查询加速层，关系库仍是主数据。

验收标准：
- 已有 entity_relation 可以同步为图边。
- 可以查询某个实体的一跳邻居。
- 可以按关系类型和置信度过滤。
- 图数据库不可用时，系统能降级返回错误说明，不影响主服务启动。

分支名：
feat/graph-service
