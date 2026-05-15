你是 KnowPilot 项目的文档导入与解析 Agent。

你的目标：
实现文件导入、URL 导入、基础解析、版本保存、Chunk 切分和导入任务状态管理。

请完成：
1. 实现文件上传接口：
   POST /api/v1/documents/import/file
2. 实现 URL 导入接口：
   POST /api/v1/documents/import/url
3. 实现文档列表接口：
   GET /api/v1/documents
4. 实现文档详情接口：
   GET /api/v1/documents/{doc_id}
5. 实现文档版本内容接口：
   GET /api/v1/documents/{doc_id}/versions/{version_id}
6. 实现文档内容保存接口：
   PUT /api/v1/documents/{doc_id}/content
7. 实现本地文件存储抽象：
   - LocalFileStorage
   - 后续可替换为 MinIOStorage
8. 实现 DocumentParserRouter。
9. 首批支持：
   - txt
   - markdown
   - pdf 基础文本提取
   - docx 基础文本提取
   - xlsx/csv 基础表格提取
10. 图片 OCR 先定义接口，可以留 TODO。
11. 实现 Markdown 结构化保存。
12. 实现 document_version。
13. 实现 document_chunk 切分。
14. 创建 task_job 记录导入任务状态。
15. 写测试覆盖：
   - txt 导入
   - md 导入
   - 重复文件 hash 检测
   - chunk 生成
   - 文档版本保存

边界：
- 不要实现向量化。
- 不要实现实体识别。
- 不要实现关系抽取。
- 不要实现前端页面。
- 不要直接调用 LLM。

验收标准：
- 上传 txt/md 文件后能生成 document、document_file、document_version、document_chunk。
- 文档可以通过接口读取。
- 修改文档后生成新版本。
- 导入失败时 task_job 中有错误信息。
- 所有解析器都有清晰接口，方便后续替换。

分支名：
feat/document-import-parser
