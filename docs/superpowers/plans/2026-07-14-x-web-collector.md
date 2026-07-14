# X Web Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Mac-resident collector that automatically ingests X account timelines and keyword searches through X Web's internal APIs without using developer API credits.

**Architecture:** Add schema-driven `x_web` source and import/heartbeat/command APIs to the existing investment backend. Run a separate TypeScript + Playwright collector on the Mac with a persistent browser profile, file-backed spool, and `launchd`; extend the existing investment sources page to configure and monitor it.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, React, TypeScript, Ant Design, Vitest, Node.js, Playwright, macOS launchd.

---

## File Map

Backend responsibilities:

- `backend/app/schemas/investment.py`: `x_web` source configuration, import, heartbeat, and command schemas.
- `backend/app/infrastructure/models.py`: persisted collector heartbeat state.
- `backend/alembic/versions/202607140001_x_web_collector.py`: collector state migration.
- `backend/app/services/investment/x_web.py`: X post normalization, idempotent import, heartbeat, and command transitions.
- `backend/app/api/v1/investment.py`: collector-facing HTTP endpoints.
- `backend/tests/test_investment_x_web.py`: API and service behavior.

Mac collector responsibilities:

- `tools/x-collector/package.json`: isolated runtime and test commands.
- `tools/x-collector/tsconfig.json`: TypeScript build settings.
- `tools/x-collector/src/types.ts`: stable internal contracts.
- `tools/x-collector/src/query-discovery.ts`: discover current X GraphQL query IDs.
- `tools/x-collector/src/session.ts`: guest and persistent-login browser sessions.
- `tools/x-collector/src/normalizer.ts`: GraphQL-to-post conversion.
- `tools/x-collector/src/account-collector.ts`: account timeline collection.
- `tools/x-collector/src/keyword-collector.ts`: latest-search collection.
- `tools/x-collector/src/spool.ts`: bounded file-backed upload queue.
- `tools/x-collector/src/backend-client.ts`: KnowPilot API client.
- `tools/x-collector/src/scheduler.ts`: due-source scheduling, jitter, and retries.
- `tools/x-collector/src/cli.ts`: `run`, `login`, `once`, `status`, `install`, and `uninstall` commands.
- `tools/x-collector/src/*.test.ts`: focused unit tests with sanitized fixtures.
- `tools/x-collector/fixtures/*.json`: bounded, credential-free X responses.
- `tools/x-collector/launchd/com.knowpilot.x-collector.plist.template`: user LaunchAgent template.

Frontend responsibilities:

- `frontend/src/services/investmentApi.ts`: `x_web` types and collector APIs.
- `frontend/src/pages/InvestmentSourcesPage.tsx`: account/keyword forms and collector status.
- `frontend/src/pages/InvestmentSourcesPage.test.tsx`: form and status tests.

Documentation responsibilities:

- `README.md`: Mac collector setup and first-login workflow.
- `.env.example`: non-secret collector configuration names.

## Task 1: Add schema-driven X Web source configuration

**Files:**
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_investment_x_web.py`

- [ ] **Step 1: Write failing schema tests**

```python
from pydantic import ValidationError

from app.schemas.investment import InvestmentSourceCreate


def test_x_web_account_source_normalizes_username():
    source = InvestmentSourceCreate.model_validate(
        {
            "source_type": "x_web",
            "name": "Elon Musk",
            "config": {"mode": "account", "username": "@elonmusk", "max_items_per_poll": 50},
            "poll_interval_seconds": 900,
        }
    )
    assert source.config["username"] == "elonmusk"
    assert source.default_info_layer == "opinion"


def test_x_web_keyword_rejects_interval_below_five_minutes():
    with pytest.raises(ValidationError):
        InvestmentSourceCreate.model_validate(
            {
                "source_type": "x_web",
                "name": "Fed",
                "config": {"mode": "keyword", "query": "Federal Reserve"},
                "poll_interval_seconds": 299,
            }
        )
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && pytest tests/test_investment_x_web.py -q`

Expected: FAIL because `SourceType.X_WEB` and discriminated source configuration do not exist.

- [ ] **Step 3: Add source config schemas and validation**

```python
class XWebAccountConfig(BaseModel):
    mode: Literal["account"]
    username: str = Field(min_length=1, max_length=64)
    max_items_per_poll: int = Field(default=50, ge=1, le=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().removeprefix("@")
        if not normalized or not normalized.replace("_", "").isalnum():
            raise ValueError("invalid X username")
        return normalized


class XWebKeywordConfig(BaseModel):
    mode: Literal["keyword"]
    query: str = Field(min_length=1, max_length=512)
    max_items_per_poll: int = Field(default=50, ge=1, le=200)


XWebSourceConfig = Annotated[
    XWebAccountConfig | XWebKeywordConfig,
    Field(discriminator="mode"),
]
```

Add `X_WEB = "x_web"` to `SourceType`. Add an `InvestmentSourceCreate.model_validator(mode="after")` that validates `config` with `TypeAdapter(XWebSourceConfig)`, stores `model_dump()` back into `config`, enforces `poll_interval_seconds >= 300`, and sets `default_info_layer = InfoLayer.OPINION` when the caller left it at the default.

- [ ] **Step 4: Run schema tests**

Run: `cd backend && pytest tests/test_investment_x_web.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/investment.py backend/tests/test_investment_x_web.py
git commit -m "feat(investment): add X web source schemas"
```

## Task 2: Add batch import schemas and idempotent service

**Files:**
- Modify: `backend/app/schemas/investment.py`
- Create: `backend/app/services/investment/x_web.py`
- Modify: `backend/app/services/investment/repositories.py`
- Modify: `backend/app/api/v1/investment.py`
- Test: `backend/tests/test_investment_x_web.py`

- [ ] **Step 1: Write failing import tests**

```python
def _post(tweet_id: str, *, likes: int = 1) -> dict[str, object]:
    return {
        "tweet_id": tweet_id,
        "author_id": "44196397",
        "author_username": "elonmusk",
        "author_name": "Elon Musk",
        "text": "Test post",
        "published_at": "2026-07-14T00:00:00Z",
        "url": f"https://x.com/elonmusk/status/{tweet_id}",
        "metrics": {"like_count": likes},
        "media": [],
    }


def test_x_post_import_is_idempotent_and_refreshes_metrics(client):
    source = client.post(
        "/api/v1/investment/sources",
        json={"source_type": "x_web", "name": "Elon", "config": {"mode": "account", "username": "elonmusk"}},
    ).json()
    first = client.post(
        "/api/v1/investment/import/x-posts",
        json={"source_id": source["id"], "collector_id": "collector_test", "items": [_post("1")]},
    )
    second = client.post(
        "/api/v1/investment/import/x-posts",
        json={"source_id": source["id"], "collector_id": "collector_test", "items": [_post("1", likes=2)]},
    )
    assert first.json()["items_created"] == 1
    assert second.json()["items_updated"] == 1
    items = client.get(f"/api/v1/investment/items?source_id={source['id']}").json()
    assert len(items) == 1
```

- [ ] **Step 2: Run the import test and verify failure**

Run: `cd backend && pytest tests/test_investment_x_web.py::test_x_post_import_is_idempotent_and_refreshes_metrics -q`

Expected: FAIL with 404 for `/import/x-posts`.

- [ ] **Step 3: Define import contracts**

```python
class XPostImportItem(BaseModel):
    tweet_id: str = Field(pattern=r"^\d+$", max_length=32)
    author_id: str | None = Field(default=None, max_length=64)
    author_username: str = Field(min_length=1, max_length=64)
    author_name: str | None = Field(default=None, max_length=255)
    text: str = Field(default="", max_length=100_000)
    published_at: datetime
    url: HttpUrl
    conversation_id: str | None = Field(default=None, max_length=32)
    lang: str | None = Field(default=None, max_length=16)
    media: list[dict[str, object]] = Field(default_factory=list, max_length=16)
    quoted_tweet: dict[str, object] | None = None
    reposted_tweet: dict[str, object] | None = None
    reply_to_tweet_id: str | None = Field(default=None, max_length=32)
    metrics: dict[str, int | None] = Field(default_factory=dict)
    raw_payload: dict[str, object] = Field(default_factory=dict)


class XPostBatchImportRequest(BaseModel):
    workspace_id: str = "ws_default"
    source_id: str
    collector_id: str = Field(min_length=1, max_length=128)
    items: list[dict[str, object]] = Field(min_length=1, max_length=200)


class XPostBatchImportResponse(BaseModel):
    items_seen: int
    items_created: int
    items_updated: int
    items_skipped: int
    errors: list[dict[str, object]] = Field(default_factory=list)
```

Keep `items` as raw dictionaries so each row can be validated with `XPostImportItem.model_validate()` independently and one malformed item does not reject the entire batch.

- [ ] **Step 4: Implement `XWebInvestmentService.import_posts`**

```python
def import_posts(self, payload: XPostBatchImportRequest) -> XPostBatchImportResponse:
    source = self.session.get(InvestmentSource, payload.source_id)
    if source is None or source.source_type != "x_web":
        raise AppError("x_source_not_found", "X web source not found", 404)

    created = updated = skipped = 0
    errors: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(payload.items):
        try:
            post = XPostImportItem.model_validate(raw_item)
            if post.tweet_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(post.tweet_id)
            result = self._upsert_post(source=source, workspace_id=payload.workspace_id, post=post)
            created += result == "created"
            updated += result == "updated"
        except (ValidationError, ValueError) as exc:
            skipped += 1
            errors.append({"index": index, "message": str(exc)[:500]})
    self.session.commit()
    return XPostBatchImportResponse(
        items_seen=len(payload.items), items_created=created, items_updated=updated,
        items_skipped=skipped, errors=errors[:20],
    )
```

Implement `_upsert_post` by computing `compute_dedupe_key("x_web", post.tweet_id, str(post.url))`. Create an `InvestmentRawItem` and call the repository for new rows. For existing rows, update source-owned title, summary, published time, media, metrics, and raw payload while leaving user-confirmed investment fields untouched. Set `source_credibility="personal_opinion"` for `x_web`.

Expose the service immediately so this task is independently usable:

```python
@router.post("/import/x-posts", response_model=XPostBatchImportResponse)
async def import_x_posts(
    payload: XPostBatchImportRequest,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> XPostBatchImportResponse:
    return XWebInvestmentService(service.session).import_posts(payload)
```

- [ ] **Step 5: Run focused backend tests**

Run: `cd backend && pytest tests/test_investment_x_web.py -q`

Expected: PASS for new, duplicate, updated, malformed-row, and wrong-source cases.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/investment.py backend/app/services/investment/x_web.py backend/app/services/investment/repositories.py backend/app/api/v1/investment.py backend/tests/test_investment_x_web.py
git commit -m "feat(investment): import X web posts idempotently"
```

## Task 3: Expose import, heartbeat, and command APIs

**Files:**
- Modify: `backend/app/infrastructure/models.py`
- Create: `backend/alembic/versions/202607140001_x_web_collector.py`
- Modify: `backend/app/schemas/investment.py`
- Modify: `backend/app/services/investment/x_web.py`
- Modify: `backend/app/api/v1/investment.py`
- Test: `backend/tests/test_investment_x_web.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_collector_heartbeat_and_manual_command(client):
    source = client.post(
        "/api/v1/investment/sources",
        json={"source_type": "x_web", "name": "Fed", "config": {"mode": "keyword", "query": "Federal Reserve"}, "poll_interval_seconds": 1800},
    ).json()
    heartbeat = client.post(
        "/api/v1/investment/x-collector/heartbeat",
        json={"collector_id": "collector_test", "version": "0.1.0", "login_status": "ready", "queue_size": 0},
    )
    command = client.post(f"/api/v1/investment/sources/{source['id']}/poll").json()
    pending = client.get("/api/v1/investment/x-collector/commands?collector_id=collector_test").json()
    assert heartbeat.status_code == 200
    assert command["status"] == "pending"
    assert pending[0]["source_id"] == source["id"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && pytest tests/test_investment_x_web.py::test_collector_heartbeat_and_manual_command -q`

Expected: FAIL because collector endpoints and state model do not exist.

- [ ] **Step 3: Add the collector state model and migration**

```python
class XCollectorState(UpdatedTimestampMixin, Base):
    __tablename__ = "x_collector_state"

    collector_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    login_status: Mapped[str] = mapped_column(String(32), nullable=False)
    queue_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text())
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

The Alembic revision is `202607140001` with `down_revision = "202607080001"`. Upgrade creates this table and an index on `heartbeat_at`; downgrade drops it.

- [ ] **Step 4: Implement command semantics using `TaskJob`**

Use `job_type="x_web_collect"`, `target_id=source.id`, and payload containing `collector_id` when claimed. `poll_source` must enqueue `x_web_collect` for `x_web` sources and keep the existing `investment_fetch` behavior for all other types. Command listing only returns pending, unexpired jobs and atomically marks them `running`. Completion updates `TaskJob.output`, source poll timestamps, and `last_error`.

```python
@router.post("/x-collector/heartbeat", response_model=XCollectorStateResponse)
async def heartbeat_x_collector(
    payload: XCollectorHeartbeat,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> XCollectorStateResponse:
    return XWebInvestmentService(service.session).heartbeat(payload)


@router.get("/x-collector/state", response_model=XCollectorStateResponse | None)
async def get_x_collector_state(
    collector_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> XCollectorStateResponse | None:
    return XWebInvestmentService(service.session).get_state(collector_id)


@router.get("/x-collector/commands", response_model=list[XCollectorCommandResponse])
async def claim_x_collector_commands(
    collector_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[XCollectorCommandResponse]:
    return XWebInvestmentService(service.session).claim_commands(collector_id)


@router.post("/x-collector/commands/{job_id}/complete", response_model=InvestmentFetchJobResponse)
async def complete_x_collector_command(
    job_id: str,
    payload: XCollectorCommandComplete,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentFetchJobResponse:
    return XWebInvestmentService(service.session).complete_command(job_id, payload)
```

- [ ] **Step 5: Run API and migration tests**

Run: `cd backend && pytest tests/test_investment_x_web.py tests/test_investment_api.py -q`

Expected: PASS.

Run: `cd backend && alembic upgrade head`

Expected: migration applies without error on the configured development database.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/models.py backend/alembic/versions/202607140001_x_web_collector.py backend/app/schemas/investment.py backend/app/services/investment/x_web.py backend/app/api/v1/investment.py backend/tests/test_investment_x_web.py
git commit -m "feat(investment): add X collector control API"
```

## Task 4: Scaffold the isolated Mac collector and normalize X responses

**Files:**
- Create: `tools/x-collector/package.json`
- Create: `tools/x-collector/tsconfig.json`
- Create: `tools/x-collector/src/types.ts`
- Create: `tools/x-collector/src/normalizer.ts`
- Create: `tools/x-collector/src/normalizer.test.ts`
- Create: `tools/x-collector/fixtures/account-timeline.json`
- Create: `tools/x-collector/fixtures/search-timeline.json`

- [ ] **Step 1: Create package metadata and test scripts**

```json
{
  "name": "@knowpilot/x-collector",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "vitest run",
    "lint": "eslint src --max-warnings=0"
  },
  "dependencies": {"playwright": "^1.61.1"},
  "devDependencies": {"@types/node": "^22.10.2", "typescript": "~5.6.3", "vitest": "^2.1.8"}
}
```

- [ ] **Step 2: Write failing normalizer tests**

```typescript
it("normalizes original, quoted, and media fields", () => {
  const posts = normalizeTimeline(accountFixture);
  expect(posts[0]).toMatchObject({
    tweet_id: "2075367885438890134",
    author_username: "elonmusk",
    url: "https://x.com/elonmusk/status/2075367885438890134",
  });
  expect(posts[0].media[0].type).toBe("photo");
});

it("deduplicates timeline entries by tweet id", () => {
  const posts = normalizeTimeline(searchFixture);
  expect(new Set(posts.map((post) => post.tweet_id)).size).toBe(posts.length);
});
```

- [ ] **Step 3: Run tests and verify failure**

Run: `cd tools/x-collector && npm install && npm test`

Expected: FAIL because `normalizeTimeline` does not exist.

- [ ] **Step 4: Implement bounded recursive extraction**

```typescript
export function normalizeTimeline(payload: unknown): XPost[] {
  const posts = new Map<string, XPost>();
  walkBounded(payload, 0, (node) => {
    const result = unwrapTweetResult(node);
    if (!result?.rest_id || !result.legacy) return;
    const post = normalizeTweetResult(result);
    posts.set(post.tweet_id, post);
  });
  return [...posts.values()].sort(
    (left, right) => Date.parse(right.published_at) - Date.parse(left.published_at),
  );
}
```

Limit recursion depth and visited nodes. Preserve only a bounded `raw_payload` projection rather than the full GraphQL response. Fixtures must be sanitized and under 200 KB each.

- [ ] **Step 5: Run tests and build**

Run: `cd tools/x-collector && npm test && npm run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/x-collector
git commit -m "feat(x-collector): normalize X timelines"
```

## Task 5: Discover GraphQL queries and collect accounts/keywords

**Files:**
- Create: `tools/x-collector/src/query-discovery.ts`
- Create: `tools/x-collector/src/query-discovery.test.ts`
- Create: `tools/x-collector/src/session.ts`
- Create: `tools/x-collector/src/account-collector.ts`
- Create: `tools/x-collector/src/keyword-collector.ts`
- Create: `tools/x-collector/src/collectors.test.ts`

- [ ] **Step 1: Write failing query discovery tests**

```typescript
it("discovers current operation ids from main.js", () => {
  const operations = discoverOperations(mainJsFixture, ["UserByScreenName", "UserTweets", "SearchTimeline"]);
  expect(operations.UserTweets.queryId).toMatch(/^[A-Za-z0-9_-]+$/);
  expect(operations.UserTweets.featureSwitches).toContain("responsive_web_graphql_timeline_navigation_enabled");
});
```

- [ ] **Step 2: Run the test and verify failure**

Run: `cd tools/x-collector && npm test -- query-discovery.test.ts`

Expected: FAIL because discovery is not implemented.

- [ ] **Step 3: Implement operation discovery with cache invalidation**

```typescript
export function discoverOperations(source: string, names: string[]): OperationMap {
  const operations: OperationMap = {};
  for (const name of names) {
    const marker = `operationName:"${name}"`;
    const offset = source.indexOf(marker);
    if (offset < 0) throw new QueryChangedError(name);
    const chunk = source.slice(Math.max(0, offset - 5000), offset + marker.length + 5000);
    const queryId = chunk.match(/queryId:"([^"]+)"/)?.[1];
    if (!queryId) throw new QueryChangedError(name);
    operations[name] = {queryId, featureSwitches: parseFeatureSwitches(chunk)};
  }
  return operations;
}
```

Cache by the `main.js` URL and clear the cache after GraphQL 400/404 or an operation-not-found response. Never hardcode query IDs or the Web bearer token.

- [ ] **Step 4: Implement guest and persistent sessions**

`GuestSession.create()` launches Chromium, listens for `/1.1/guest/activate.json`, captures the temporary Web authorization header and guest token in memory, and closes the page after collection. `PersistentSession` uses `launchPersistentContext(profileDir)` and exposes `loginStatus()` without reading cookie files directly. Secrets must never be logged or serialized.

- [ ] **Step 5: Implement collectors against injectable transport**

```typescript
export class AccountCollector {
  constructor(private readonly transport: XWebTransport, private readonly discovery: QueryDiscovery) {}

  async collect(source: AccountSource): Promise<XPost[]> {
    const user = await this.transport.query("UserByScreenName", {screen_name: source.username});
    const userId = extractUserId(user);
    const timeline = await this.transport.query("UserTweets", {
      userId,
      count: source.max_items_per_poll,
      includePromotedContent: false,
      withVoice: true,
    });
    return normalizeTimeline(timeline).slice(0, source.max_items_per_poll);
  }
}
```

`KeywordCollector` runs `SearchTimeline` with `product="Latest"`. Map 401/403 to `auth_required`, 429 to `rate_limited`, and operation failures to `query_changed`.

- [ ] **Step 6: Run collector tests and build**

Run: `cd tools/x-collector && npm test && npm run build`

Expected: PASS with mocked transport; no live X calls in automated tests.

- [ ] **Step 7: Commit**

```bash
git add tools/x-collector/src tools/x-collector/fixtures
git commit -m "feat(x-collector): collect accounts and keywords"
```

## Task 6: Add spool, backend client, retries, and scheduler

**Files:**
- Create: `tools/x-collector/src/spool.ts`
- Create: `tools/x-collector/src/spool.test.ts`
- Create: `tools/x-collector/src/backend-client.ts`
- Create: `tools/x-collector/src/backend-client.test.ts`
- Create: `tools/x-collector/src/scheduler.ts`
- Create: `tools/x-collector/src/scheduler.test.ts`

- [ ] **Step 1: Write failing spool and retry tests**

```typescript
it("replays queued batches oldest first after restart", async () => {
  const spool = new FileSpool(tempDir, {maxBytes: 1_000_000});
  await spool.enqueue(batchAt("2026-07-14T01:00:00Z"));
  await spool.enqueue(batchAt("2026-07-14T02:00:00Z"));
  const reopened = new FileSpool(tempDir, {maxBytes: 1_000_000});
  expect((await reopened.peek()).created_at).toBe("2026-07-14T01:00:00Z");
});

it("stops collecting when the spool quota is exceeded", async () => {
  await expect(spool.enqueue(oversizedBatch)).rejects.toThrow(SpoolQuotaError);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd tools/x-collector && npm test -- spool.test.ts scheduler.test.ts`

Expected: FAIL because spool and scheduler do not exist.

- [ ] **Step 3: Implement an atomic file spool**

Write each batch to a temporary file, `fsync`, then rename to `<createdAt>-<uuid>.json`. Keep an index in memory rebuilt from filenames at startup. Delete only after a successful backend response. Refuse new writes before exceeding `maxBytes`.

- [ ] **Step 4: Implement backend client and scheduler**

```typescript
export async function withRetry<T>(operation: () => Promise<T>, classify: (error: unknown) => RetryDecision): Promise<T> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try { return await operation(); }
    catch (error) {
      const decision = classify(error);
      if (!decision.retry) throw error;
      await delay(decision.retryAfterMs ?? Math.min(60_000, 1_000 * 2 ** attempt));
    }
  }
  throw new Error("retry limit reached");
}
```

The scheduler polls source commands and enabled `x_web` sources, applies 30-90 seconds of jitter, prevents overlapping runs per source, drains the spool before new collection, and sends heartbeat every 60 seconds. `auth_required` and `challenge_required` are terminal until login state changes.

- [ ] **Step 5: Run collector tests**

Run: `cd tools/x-collector && npm test && npm run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/x-collector/src
git commit -m "feat(x-collector): add durable scheduling and upload"
```

## Task 7: Add CLI and macOS launchd installation

**Files:**
- Create: `tools/x-collector/src/config.ts`
- Create: `tools/x-collector/src/cli.ts`
- Create: `tools/x-collector/src/cli.test.ts`
- Create: `tools/x-collector/launchd/com.knowpilot.x-collector.plist.template`
- Modify: `tools/x-collector/package.json`

- [ ] **Step 1: Write failing CLI tests**

```typescript
it("renders a user LaunchAgent without secrets in arguments", async () => {
  const plist = renderLaunchAgent({nodePath: "/opt/homebrew/bin/node", appPath: "/repo/dist/cli.js"});
  expect(plist).toContain("com.knowpilot.x-collector");
  expect(plist).not.toContain("KNOWPILOT_COLLECTOR_TOKEN");
});
```

- [ ] **Step 2: Run test and verify failure**

Run: `cd tools/x-collector && npm test -- cli.test.ts`

Expected: FAIL because the CLI is missing.

- [ ] **Step 3: Implement configuration and commands**

Use `~/Library/Application Support/KnowPilot/x-collector` by default. Support:

```text
x-collector login
x-collector run
x-collector once --source <id>
x-collector status
x-collector install
x-collector uninstall
```

`login` opens the dedicated persistent profile in headed mode and waits for the user to finish login. `install` writes the rendered plist to `~/Library/LaunchAgents/com.knowpilot.x-collector.plist`, runs `launchctl bootstrap gui/$UID`, and is idempotent. Environment secrets live in a mode-0600 local env file referenced by `EnvironmentVariables`; they must not appear in command arguments or logs.

- [ ] **Step 4: Run CLI tests and build**

Run: `cd tools/x-collector && npm test && npm run build`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/x-collector
git commit -m "feat(x-collector): add Mac service CLI"
```

## Task 8: Add X Web configuration and status to the frontend

**Files:**
- Modify: `frontend/src/services/investmentApi.ts`
- Modify: `frontend/src/pages/InvestmentSourcesPage.tsx`
- Modify: `frontend/src/pages/InvestmentSourcesPage.test.tsx`

- [ ] **Step 1: Write failing UI tests**

```typescript
it("creates an X Web keyword subscription", async () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", {name: "新增数据源"}));
  fireEvent.mouseDown(screen.getByRole("combobox", {name: "类型"}));
  fireEvent.click(await screen.findByText("X / 网页采集"));
  fireEvent.mouseDown(screen.getByRole("combobox", {name: "采集模式"}));
  fireEvent.click(await screen.findByText("关键词主题"));
  fireEvent.change(screen.getByLabelText("关键词"), {target: {value: "Federal Reserve"}});
  expect(screen.getByLabelText("抓取频率(秒)")).toHaveValue("1800");
});

it("shows collector login state", async () => {
  renderPageWithCollector({login_status: "auth_required"});
  expect(await screen.findByText("需要重新登录")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd frontend && npm test -- InvestmentSourcesPage.test.tsx`

Expected: FAIL because `x_web` and collector state are not rendered.

- [ ] **Step 3: Add frontend contracts and API calls**

Add `"x_web"` to `SourceType`, typed account/keyword config unions, `XCollectorState`, `XCollectorCommand`, and methods for state, commands, and heartbeat-derived status. Keep all X credentials absent from frontend types.

- [ ] **Step 4: Implement form and status UI**

Add `X / 网页采集` to the type selector. Use a segmented account/keyword mode control, `@username` or query input, and numeric frequency with a minimum of 300 seconds. Show collector online/offline, login ready/auth required, queue size, last success, and bounded last error. For `x_web`, “立即抓取” creates a collector command and polls the existing job endpoint.

- [ ] **Step 5: Run frontend tests and build**

Run: `cd frontend && npm test -- InvestmentSourcesPage.test.tsx && npm run lint && npm run build`

Expected: PASS; Vite may retain the existing chunk-size warning.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/investmentApi.ts frontend/src/pages/InvestmentSourcesPage.tsx frontend/src/pages/InvestmentSourcesPage.test.tsx
git commit -m "feat(frontend): configure X web collector"
```

## Task 9: Document, run live acceptance, and verify the full repository

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `tools/x-collector/README.md`

- [ ] **Step 1: Document the exact Mac setup**

Document Node installation, `npm install`, `npx playwright install chromium`, collector environment variables, `npm run build`, `x-collector login`, `x-collector install`, `x-collector status`, log location, uninstall, and recovery from `auth_required`. State that X internal APIs are unsupported and may change.

- [ ] **Step 2: Run static secret checks**

Run: `rg -n "(Bearer [A-Za-z0-9]|ct0=|auth_token=|guest_token\":|cpa-key|BRIGHTDATA_API_KEY=.+)" tools/x-collector backend frontend README.md .env.example`

Expected: no credential values; test fixture field names may be allowed only when values are visibly redacted.

- [ ] **Step 3: Run backend verification**

Run: `cd backend && pytest tests/test_investment_x_web.py tests/test_investment_api.py tests/test_investment_fetch_service.py -q`

Expected: PASS.

Run: `cd backend && ruff check app tests && mypy app`

Expected: PASS, or document pre-existing mypy failures separately without hiding new failures.

- [ ] **Step 4: Run collector verification**

Run: `cd tools/x-collector && npm test && npm run build`

Expected: PASS.

- [ ] **Step 5: Run frontend verification**

Run: `cd frontend && npm test && npm run lint && npm run build`

Expected: PASS; the existing Vite chunk-size warning is acceptable.

- [ ] **Step 6: Perform bounded live acceptance**

Create account sources for Trump, Jensen Huang, and Elon Musk, plus a keyword source for `Federal Reserve OR 美联储`. Run each source once with `max_items_per_poll=5`. Verify each returns five or fewer newest items, original links open, media is present when supplied, and a second run creates zero duplicates. Do not include live response payloads or session data in Git.

- [ ] **Step 7: Install the Mac LaunchAgent and verify recovery**

Run `x-collector install`, confirm `x-collector status` reports online, stop the process once, and verify `launchd` restarts it. Temporarily make the backend unavailable, collect one bounded batch, restore the backend, and verify the spool uploads oldest-first.

- [ ] **Step 8: Commit documentation**

```bash
git add README.md .env.example tools/x-collector/README.md
git commit -m "docs: add X web collector operations"
```

- [ ] **Step 9: Final review**

Run `git status --short` and `git diff HEAD~8 --check`. Confirm only expected source, tests, migration, documentation, and lockfiles changed; preserve unrelated `.DS_Store` files.
