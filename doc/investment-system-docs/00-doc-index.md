# 投资信息系统补充文档索引

日期：2026-07-02  
项目：KnowPilot / yi5an/my_knowlage  
目标：指导 GLM-5.2 Agent 在现有项目中开发投资信息系统第一、第二阶段。

## 文档列表

1. `01-real-data-sources.md`
   - 真实数据源清单。
   - 官方接口、必要环境变量、抓取频率、限流要求。
   - 明确禁止产品逻辑使用 mock 数据。

2. `02-data-flow-architecture.md`
   - 从采集、解析、去重、入库、摘要、实体抽取、投资判断到前端展示的数据流。
   - 描述同步/异步边界、错误处理、幂等策略。

3. `03-frontend-transformation.md`
   - 前端页面、路由、组件、API service 改造。
   - 适配现有 React + Vite + Ant Design 项目结构。

4. `04-technical-implementation.md`
   - 后端模型、Alembic 迁移、Pydantic schema、API、service、fetcher、worker 的技术实现。
   - 文件路径、类名、接口契约和测试要求。

5. `05-glm52-agent-development-plan.md`
   - 给 GLM-5.2 Agent 执行的分阶段任务清单。
   - 每个任务包含输入文档、修改文件、测试命令、验收标准。

## 总体原则

1. 不从零搭建独立系统，在 KnowPilot 内新增 `investment` 模块。
2. 产品环境不得使用 mock 数据源。
3. 测试可以使用 fixture、临时文件、HTTP fake client，但不能把 mock client 接入生产依赖。
4. 所有投资信息必须保留 `source_url`、`source_name`、`published_at` 和原始 payload 摘要。
5. YouTube、研报、社媒等观点层信息默认进入 `opinion`，不能直接当事实。
6. 官方公告和宏观数据优先进入 `primary_source` 或 `macro_calendar`。
7. 自动判断只产生 `suggested_*` 字段，最终判断字段必须允许用户修改。

