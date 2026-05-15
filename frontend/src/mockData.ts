export const workspaceStats = [
  { label: "Documents", value: "328", tone: "blue" },
  { label: "Entities", value: "2,641", tone: "green" },
  { label: "Relations", value: "7,820", tone: "gold" },
  { label: "Research tasks", value: "9", tone: "purple" },
];

export const recentActivities = [
  "Imported semiconductor-industry-chain.md",
  "Confirmed entity merge: NVIDIA / NVDA",
  "Created relation type: supplies_to",
  "Drafted report: AI compute supply chain risks",
];

export const actionItems = [
  { title: "5 entities need confirmation", detail: "NVIDIA, NVDA, and 英伟达 may refer to one entity." },
  { title: "3 low-confidence relations", detail: "Evidence snippets are available for review." },
  { title: "2 import tasks failed", detail: "OCR timeout, ready for retry." },
];

export const importJobs = [
  { name: "AI Agent 本地知识库 PRD.pdf", status: "Parsing", progress: 62 },
  { name: "semiconductor-chain.md", status: "Entity extraction", progress: 88 },
  { name: "meeting-notes.txt", status: "Queued", progress: 15 },
];

export const documents = [
  {
    id: "doc_001",
    title: "AI Agent 本地知识库 PRD",
    type: "Markdown",
    status: "Indexed",
    tags: ["RAG", "Graph", "Agent"],
    updatedAt: "Today 10:42",
  },
  {
    id: "doc_002",
    title: "AI compute supply chain research",
    type: "PDF",
    status: "Review",
    tags: ["NVIDIA", "TSMC", "Semiconductor"],
    updatedAt: "Yesterday 18:12",
  },
  {
    id: "doc_003",
    title: "NotebookLM export checklist",
    type: "Text",
    status: "Draft",
    tags: ["Export", "NotebookLM"],
    updatedAt: "May 14",
  },
];

export const graphNodes = [
  { id: "nvidia", label: "NVIDIA", x: 45, y: 40, className: "node-primary" },
  { id: "tsmc", label: "TSMC", x: 18, y: 24, className: "node-blue" },
  { id: "asml", label: "ASML", x: 12, y: 68, className: "node-green" },
  { id: "gpu", label: "GPU", x: 68, y: 24, className: "node-gold" },
  { id: "cloud", label: "Cloud", x: 72, y: 68, className: "node-purple" },
];

export const researchTasks = [
  { title: "AI compute supply chain", status: "Running", progress: 64 },
  { title: "Local-first knowledge base landscape", status: "Draft", progress: 38 },
  { title: "NotebookLM enterprise export", status: "Planned", progress: 10 },
];

export const citations = [
  { source: "AI Agent 本地知识库 PRD", quote: "GraphRAG links chunks, entities, and relations." },
  { source: "AI Pipeline Design", quote: "Every generated result stores evidence and confidence." },
];

