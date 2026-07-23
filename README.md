# KnowPilot

KnowPilot is a local-first AI knowledge base. This repository currently contains the project bootstrap, database model layer, CI checks, fixtures, and development documentation needed for parallel Agent work.

## Prerequisites

- Python 3.12
- Node.js 20+
- Docker and Docker Compose

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

Health check:

```bash
curl http://localhost:8010/api/v1/health
```

Expected response:

```json
{"status":"ok"}
```

Backend checks:

```bash
cd backend
alembic upgrade head
pytest
ruff check .
mypy app
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run test
npm run build
```

## Docker Compose

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Services:

- Backend: http://localhost:8010
- Frontend: http://localhost:5173
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Current Scope

This repository intentionally does not yet implement document import, AI provider calls, RAG, graph synchronization, or research workflows. Those belong to later Agent tasks.

## Development Docs

- [Local development guide](docs/development/local-dev-guide.md)
- [Testing guide](docs/development/testing-guide.md)
- [API conventions](docs/development/api-conventions.md)
- [Error codes](docs/development/error-codes.md)

## X 网页采集器（Mac）

X 网页采集器运行在一台长期在线的 Mac 上，通过持久化 Playwright 浏览器会话访问 X 的网页内部接口，不使用官方开发者 API 配额。账号采集可使用访客链路；关键词采集需要先在 Mac 上登录 X。

```bash
cd tools/x-collector
npm install
npx playwright install chromium
npm run build
node dist/cli.js login
```

登录完成后，在 `~/Library/Application Support/KnowPilot/x-collector/.env` 写入配置（`install` 会生成 `.env.example`）：

```dotenv
KNOWPILOT_URL=http://127.0.0.1:8010
X_COLLECTOR_ID=my-mac
X_COLLECTOR_TOKEN=
```

确认 `KNOWPILOT_URL` 指向实际 KnowPilot 后端，再执行：

```bash
node dist/cli.js install
```

这只会安装并启动 `com.knowpilot.x-collector` 自己的 LaunchAgent。日志在 `~/Library/Logs/KnowPilot/`，状态可用 `node dist/cli.js status` 查看；停止并移除它使用 `node dist/cli.js uninstall`。前端“数据源”页会显示采集器在线、需要重新登录或验证的状态。
# Model management

Use **设置 → 模型管理** to save provider addresses, models, default capability routes and API Keys for LLM, Embedding, ASR and OCR. API Keys are Fernet-encrypted in the database and are never returned by the API. Set a stable `MODEL_ENCRYPTION_KEY` in the deployment environment before saving a key; existing LLM/Embedding/ASR/OCR environment variables remain a first-deployment fallback when no database route is selected.

## YouTube 直播

预约中和正在直播的 YouTube 视频会被忽略，不会创建历史记录或总结任务；已结束的直播回放会按普通视频处理。

## 全局 AI 陪读

点击页面右下角的 **AI 陪读** 可在不离开当前页面的情况下提问。阅读页、YouTube 总结详情页会自动绑定当前资料；在信息差系统中点击一条信号后，会绑定该信号。

对话按内容对象持久保存；点击 **新一轮** 会写入一个轮次分界，方便围绕同一资料重新开始讨论。回答和主动提示均附带当前内容的原始证据，并会检索同一工作区内匹配的资料作为平台内佐证；没有证据时，助手会明确说明资料不足，而不会把推测当作结论。
