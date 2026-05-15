你是 KnowPilot 项目的向量检索与 RAG Agent。

你的目标：
实现 Embedding 抽象、向量库适配、混合搜索接口和带引用的 RAG 问答。

请完成：
1. 创建 EmbeddingClient 抽象接口。
2. 创建 MockEmbeddingClient 用于测试。
3. 创建 OllamaEmbeddingClient 或 OpenAICompatibleEmbeddingClient，但不要硬编码 API Key。
4. 创建 VectorStore 抽象接口。
5. 创建 QdrantVectorStore 适配器。
6. 创建可测试的 InMemoryVectorStore。
7. 实现 chunk 向量化任务：
   - 输入 document_chunk
   - 输出 vector_id
8. 实现搜索接口：
   POST /api/v1/search
9. 搜索先支持：
   - keyword
   - vector
   - hybrid 占位
10. 创建 RerankerClient 抽象接口。
11. 创建 MockRerankerClient。
12. 实现 RAG 问答接口：
   POST /api/v1/chat/query
13. RAG 回答必须返回：
   - answer
   - citations
   - related_entities
   - used_chunks
14. 如果没有检索到可靠内容，必须返回“知识库中没有足够证据”，不能编造。
15. 添加测试：
   - embedding mock
   - vector search
   - search API
   - RAG 无证据场景
   - RAG 带引用场景

边界：
- 不要实现文档导入。
- 不要实现实体抽取。
- 不要实现图谱查询。
- 不要实现前端页面。
- 可以读取 document_chunk，但不要修改文档导入逻辑。

验收标准：
- 可以对已有 chunk 建立向量索引。
- 可以通过 /search 搜到相关 chunk。
- /chat/query 返回答案和引用。
- 无证据时不胡编。
- 模型 Provider 可替换。

分支名：
feat/rag-search
