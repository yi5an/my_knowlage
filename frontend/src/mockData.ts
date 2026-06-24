export const workspaceStats = [
  { label: "文档", value: "328", tone: "blue" },
  { label: "实体", value: "2,641", tone: "green" },
  { label: "关系", value: "7,820", tone: "gold" },
  { label: "研究任务", value: "9", tone: "purple" },
];

export const recentActivities = [
  "导入了 semiconductor-industry-chain.md",
  "确认实体合并：NVIDIA / NVDA",
  "创建关系类型：supplies_to",
  "起草报告：AI 算力供应链风险",
];

export const actionItems = [
  { title: "5 个实体待确认", detail: "NVIDIA、NVDA 与 英伟达 可能指向同一实体。" },
  { title: "3 条低置信度关系", detail: "可查看证据片段进行审阅。" },
  { title: "2 个导入任务失败", detail: "OCR 超时，可重试。" },
];

export const importJobs = [
  { name: "AI Agent 本地知识库 PRD.pdf", status: "解析中", progress: 62 },
  { name: "semiconductor-chain.md", status: "实体抽取中", progress: 88 },
  { name: "meeting-notes.txt", status: "排队中", progress: 15 },
];

export const documents = [
  {
    id: "doc_001",
    title: "AI Agent 本地知识库 PRD",
    type: "Markdown",
    status: "已索引",
    tags: ["RAG", "Graph", "Agent"],
    updatedAt: "今天 10:42",
  },
  {
    id: "doc_002",
    title: "AI 算力供应链研究",
    type: "PDF",
    status: "审阅中",
    tags: ["NVIDIA", "TSMC", "半导体"],
    updatedAt: "昨天 18:12",
  },
  {
    id: "doc_003",
    title: "NotebookLM 导出清单",
    type: "文本",
    status: "草稿",
    tags: ["导出", "NotebookLM"],
    updatedAt: "5 月 14 日",
  },
];

export const graphNodes = [
  { id: "nvidia", label: "NVIDIA", x: 45, y: 40, className: "node-primary" },
  { id: "tsmc", label: "台积电", x: 18, y: 24, className: "node-blue" },
  { id: "asml", label: "ASML", x: 12, y: 68, className: "node-green" },
  { id: "gpu", label: "GPU", x: 68, y: 24, className: "node-gold" },
  { id: "cloud", label: "云计算", x: 72, y: 68, className: "node-purple" },
];

export const researchTasks = [
  { title: "AI 算力供应链", status: "运行中", progress: 64 },
  { title: "本地优先知识库调研", status: "草稿", progress: 38 },
  { title: "NotebookLM 企业导出", status: "已计划", progress: 10 },
];

export const citations = [
  { source: "AI Agent 本地知识库 PRD", quote: "GraphRAG 将文本块、实体和关系关联起来。" },
  { source: "AI 流水线设计", quote: "每个生成结果都保留证据与置信度。" },
];
