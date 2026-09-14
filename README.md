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

### Event/conclusion provenance API

The provenance graph keeps its durable source of truth in PostgreSQL and treats the configured graph store as a rebuildable read projection. Every request is scoped by `workspace_id`.

- `GET /api/v1/provenance/overview` returns the three-layer overview.
- `GET /api/v1/provenance/nodes/{node_id}/trace?direction=up|down` returns a focused path while preserving the canonical evidence-to-conclusion edge direction.
- `GET /api/v1/provenance/edges/{edge_id}` returns rationale and immutable evidence anchors.
- `POST /api/v1/provenance/edges/{edge_id}/review` confirms, rejects, or marks a versioned edge as conflicted using optimistic locking.
- `POST /api/v1/provenance/conclusions` creates a research or investment conclusion.
- `POST /api/v1/provenance/rebuild` enqueues an asynchronous workspace rebuild and returns immediately.
- `GET /api/v1/provenance/jobs/{job_id}` reports rebuild progress and partial failures.

Example rebuild:

```bash
curl -X POST http://localhost:8010/api/v1/provenance/rebuild \
  -H 'content-type: application/json' \
  -d '{"workspace_id":"ws_default","force":false}'
```

The generic `task_job` worker registers persisted anchors, events, and conclusions, preserves reviewed edge versions, and refreshes the graph projection. A graph-store outage is surfaced as explicit degraded query metadata; PostgreSQL provenance rows remain authoritative.

### True 3D provenance controls

Open `/provenance` for the independent WebGL three-layer view. The controls are:

- drag with the left mouse button to rotate;
- drag with Shift-left, middle, or right mouse button to pan;
- use the mouse wheel to zoom toward the pointer;
- single-click a node to focus and load its evidence path, or click a relation to open its audit record;
- double-click empty canvas space to reset the camera;
- use arrow keys to pan, `+`/`-` to zoom, `R` to reset, and `Escape` to clear selection when the canvas has keyboard focus.

The renderer lowers label density and device-pixel ratio for large graphs or constrained GPUs without dropping the selected path. The operating system’s reduced-motion preference disables path particles and camera tweening. If WebGL is unavailable—or on a narrow screen—the page shows an explicit read-only three-layer fallback; users can still inspect nodes and evidence and may opt into 3D manually.

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

The repository includes document import, provider abstractions, RAG, graph synchronization, research workflows, and the schema-first provenance backend. See the development docs for feature-specific contracts and remaining limitations.

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

## YouTube Cookie 设置

当 YouTube 提示“确认你不是机器人”时，在 **设置 → YouTube 访问 Cookie** 粘贴
`youtube.com` 的 Netscape/Mozilla 格式 Cookie 文本。生产环境将其保存在仅后端可访问的
`backend_private` Docker 命名卷中，前端、数据库、日志和 Git 都不会保存或回显 Cookie。

建议使用专用 Google 账号的无痕浏览器窗口，在与服务器相同的代理出口完成验证后再导出
Cookie。保存后可以使用“测试当前 Cookie”验证；Cookie 过期或代理出口变化时，替换为新导出的
文本即可。

## 全局 AI 陪读

点击页面右下角的 **AI 陪读** 可在不离开当前页面的情况下提问。阅读页、YouTube 总结详情页会自动绑定当前资料；在信息差系统中点击一条信号后，会绑定该信号。

对话按内容对象持久保存；点击 **新一轮** 会写入一个轮次分界，方便围绕同一资料重新开始讨论。回答和主动提示均附带当前内容的原始证据，并会检索同一工作区内匹配的资料作为平台内佐证；没有证据时，助手会明确说明资料不足，而不会把推测当作结论。

## 投资机会回填与运行观测

机会发现回填默认按工作区执行，输出一行 JSON（`created`、`skipped`、`failed`、`seen` 和 `failure_reasons`），可安全重复运行。`--dry-run` 只计算将要创建的任务/候选，不写入数据库；`--as-of` 是 ISO-8601 截止时间，历史回填不会读取截止时间之后的资料。

```bash
cd backend
python -m scripts.backfill_person_impact \
  --workspace-id ws_default --limit 500 \
  --as-of 2026-09-15T00:00:00+00:00 --dry-run
python -m scripts.backfill_opportunity_candidates \
  --workspace-id ws_default --limit 500 --dry-run
```

人物影响只接受 `human_source`/`expert_opinion` 中带有真实 `person_source_id` 和唯一显式 `symbol`/`ticker` 的条目；不会从正文猜账号或从主题推断股票。机会候选只接受来源快照中完整填写的 `catalyst`、`risk_flags`、`invalidation_conditions` 等 gate 字段，缺失时计入 `skipped`，不会生成虚假假设。失败会保留在 JSON 的 `failure_reasons` 中，并在 `TaskJob.error_message` 中显示。

### 数据提供商与任务

人物事件研究默认使用 Stooq 日线接口（`MARKET_DATA_BASE_URL`，默认 `https://stooq.com`），交易所时区默认 `America/New_York`。日线数据通常有收盘后延迟；每个事件保存 provider、请求区间、时区、缺失交易日、复权价是否为原始价和 `complete`/`partial`/`missing`/`stale`/`invalid` 质量状态。常见可见失败信息包括 `market provider error`（超时或限流）、`market bars missing`、`未能确定唯一标的` 和 `搜索服务未配置`。

`person_impact_refresh` 是异步 `TaskJob` 类型；机会候选回填是受 gate 保护的同步命令；推荐校准由 `OutcomeService.recalculate_recommendation_weights` 执行，并只使用 `observed_at <= as_of` 的结果。暂停推荐请在推荐记录上使用 `dismissed`/`paused` 状态，保留其来源、事件和结果证据，不要删除行。

### 迁移回滚与历史重建

上线前先在备份数据库执行：

```bash
cd backend
alembic upgrade 202609140002
# 回滚机会/人物影响/推荐表（不会删除旧投资资料）
alembic downgrade 202609030002
# 需要恢复时
alembic upgrade 202609140002
```

要重建历史人物 profile，使用相同 `--workspace-id` 和 `--as-of` 运行 `backfill_person_impact`，让新任务携带截止时间并通过 worker 处理；digest 快照则在截止时间对应的数据库连接上调用 `InvestmentService.create_digest_snapshot`。快照是追加写入的，旧快照不会被覆盖；回填前请记录 JSON 输出和失败原因以便审计。
