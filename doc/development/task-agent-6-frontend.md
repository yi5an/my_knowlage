你是 KnowPilot 项目的前端 Agent。

你的目标：
根据 UI/UX 原型实现前端基础页面和接口调用骨架。

请完成：
1. 使用 React + TypeScript + Vite。
2. 创建全局布局：
   - 左侧导航
   - 顶部搜索栏
   - 主内容区
3. 页面包括：
   - Dashboard 首页工作台
   - Import 导入中心
   - Library 知识库
   - Reader 阅读标注
   - Graph 知识图谱
   - Search 智能搜索
   - Research 深度研究
   - Entity 实体详情
   - NotebookLM 对接
   - Settings 设置
4. 首页采用轻量工作台设计：
   - 继续上次工作
   - 今天需要处理
   - 快速开始
   - 最近活动
   - 知识库状态
   - 功能入口地图
5. 不要把所有功能堆在首页。
6. 创建 API client：
   - documentApi.ts
   - searchApi.ts
   - entityApi.ts
   - graphApi.ts
   - researchApi.ts
   - annotationApi.ts
7. 使用 mock 数据先完成页面。
8. 导入中心支持：
   - 拖拽区域 UI
   - URL 输入 UI
   - 导入任务队列 UI
9. 阅读器支持：
   - 三栏布局
   - 目录
   - 文档正文
   - AI 助手/备注面板
10. 图谱页面可以先用静态 mock 节点。
11. 搜索页支持展示 AI 答案和引用。
12. 深度研究页支持任务列表、报告草稿、Agent 过程。
13. 添加基础前端测试或组件快照测试。
14. npm run build 必须成功。

边界：
- 不要实现后端业务。
- 不要直接调用真实 LLM。
- 不要在前端硬编码 API Key。
- 不要做复杂图谱算法，只做 UI 和接口预留。

验收标准：
- 所有页面可访问。
- 页面风格与 HTML 原型一致或接近。
- 前端 build 成功。
- API 调用层集中管理。
- 首页不重复其他页面完整功能。

分支名：
feat/frontend-shell-pages
