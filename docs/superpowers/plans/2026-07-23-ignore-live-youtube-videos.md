# Ignore Live YouTube Videos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exclude scheduled and currently live YouTube broadcasts before they enter KnowPilot history or summary processing.

**Architecture:** Extend `VideoMeta` with YouTube's `snippet.liveBroadcastContent`, then use that typed classification at the discovery and manual-submission boundaries. Existing failure rows caused by a scheduled/live broadcast become `ignored_live`, which is hidden from history and excluded from retry scans.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, React/TypeScript, pytest, Vitest.

---

### Task 1: Add typed broadcast metadata and fetcher mapping

**Files:**
- Modify: `backend/app/schemas/youtube.py:68-80`
- Modify: `backend/app/services/youtube/fetcher.py:171-211`
- Modify: `backend/app/services/youtube/fetcher.py:338-372`
- Modify: `backend/tests/test_youtube_fetch_chain.py`

- [ ] **Step 1: Write the failing fetcher test**

Add a mocked Data API response containing all three API values and assert the typed value is preserved:

```python
def test_fetcher_maps_live_broadcast_content() -> None:
    fetcher = _fetcher_with_video_response(
        {
            "id": "upcoming123",
            "snippet": {
                "title": "Upcoming stream",
                "liveBroadcastContent": "upcoming",
                "thumbnails": {},
            },
            "contentDetails": {"duration": "PT0S"},
        }
    )

    meta = fetcher.fetch_video("upcoming123")

    assert meta.live_broadcast_content == "upcoming"
    assert meta.is_live_broadcast is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_youtube_fetch_chain.py::test_fetcher_maps_live_broadcast_content -v`

Expected: FAIL because `VideoMeta` has no `live_broadcast_content` field.

- [ ] **Step 3: Add the schema field and map the YouTube API value**

In `VideoMeta`, define a safe typed contract that treats absent or unrecognised values as ordinary videos:

```python
LiveBroadcastContent = Literal["none", "live", "upcoming"]

class VideoMeta(BaseModel):
    # existing fields
    live_broadcast_content: LiveBroadcastContent = "none"

    @property
    def is_live_broadcast(self) -> bool:
        return self.live_broadcast_content in ("live", "upcoming")
```

Add a small `_live_broadcast_content(value: object) -> LiveBroadcastContent`
normalizer in `fetcher.py`, then pass it in both Data API implementations:

```python
live_broadcast_content=_live_broadcast_content(snippet.get("liveBroadcastContent")),
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_youtube_fetch_chain.py::test_fetcher_maps_live_broadcast_content -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/youtube.py backend/app/services/youtube/fetcher.py backend/tests/test_youtube_fetch_chain.py
git commit -m "feat: classify live YouTube metadata"
```

### Task 2: Filter live videos before subscription persistence and jobs

**Files:**
- Modify: `backend/app/services/youtube/subscription_service.py:78-110, 190-255`
- Modify: `backend/tests/test_subscription_service.py`

- [ ] **Step 1: Write the failing discovery test**

Use the fake fetcher with one `upcoming`, one `live`, and one `none` metadata
record. Assert the discovery response only contains the ordinary video and
that only one `Video` and one `youtube_summary` task exist:

```python
def test_discovery_ignores_scheduled_and_live_broadcasts(session: Session) -> None:
    service = _service_with_metas(
        session,
        [
            _meta("upcoming", live_broadcast_content="upcoming"),
            _meta("live-now", live_broadcast_content="live"),
            _meta("replay", live_broadcast_content="none"),
        ],
    )

    discovered = service.discover_new_videos(workspace_id="ws_default", force=True)

    assert [meta.video_id for _, metas in discovered for meta in metas] == ["replay"]
    assert session.scalars(select(Video.video_id)).all() == ["replay"]
    assert session.query(TaskJob).count() == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_subscription_service.py::test_discovery_ignores_scheduled_and_live_broadcasts -v`

Expected: FAIL because all three records are staged.

- [ ] **Step 3: Filter at both subscription paths**

Add one focused helper in `SubscriptionService`:

```python
@staticmethod
def _without_live_broadcasts(metas: list[VideoMeta]) -> list[VideoMeta]:
    return [meta for meta in metas if not meta.is_live_broadcast]
```

Apply it immediately after every `fetch_latest_videos()` result, before
`_filter_new()`, in `discover_new_videos()` and `_poll_one()`. Keep
`_record_success(sub, metas)` using the original result so polling cursors
advance over ignored broadcasts and do not rediscover them forever.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_subscription_service.py::test_discovery_ignores_scheduled_and_live_broadcasts -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/youtube/subscription_service.py backend/tests/test_subscription_service.py
git commit -m "feat: skip live broadcasts during channel discovery"
```

### Task 3: Ignore manual live submissions without creating rows or tasks

**Files:**
- Modify: `backend/app/api/v1/youtube.py:240-320, 972-1005`
- Modify: `backend/app/schemas/youtube.py:265-270`
- Modify: `frontend/src/pages/YouTubeHubPage.tsx:190-235`
- Modify: `frontend/src/services/youtubeApi.ts`
- Test: `backend/tests/test_youtube_api.py`
- Test: `frontend/src/pages/YouTubeHubPage.test.tsx`

- [ ] **Step 1: Write the failing backend API test**

Override the route's fetcher factory with a fake that returns `upcoming` and
assert no persistence or enqueue occurs:

```python
def test_manual_upcoming_live_video_is_ignored(client: TestClient, db_session: Session) -> None:
    _set_manual_video_meta(_meta("scheduled123", live_broadcast_content="upcoming"))

    response = client.post(
        "/api/v1/youtube/summarize",
        json={"workspace_id": "ws_default", "url": "https://youtu.be/scheduled123"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored_live"
    assert response.json()["task_job_id"] == ""
    assert db_session.query(Video).filter_by(video_id="scheduled123").count() == 0
    assert db_session.query(TaskJob).count() == 0
```

- [ ] **Step 2: Run the API test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_youtube_api.py::test_manual_upcoming_live_video_is_ignored -v`

Expected: FAIL because the current endpoint persists a pending row before the
background worker fetches metadata.

- [ ] **Step 3: Preflight metadata before manual persistence**

Add an API-local helper that calls the configured fetcher once. If it returns
`meta.is_live_broadcast`, return a `ManualSummaryResponse` without opening a
task:

```python
return ManualSummaryResponse(
    video_id=video_id,
    document_id="",
    task_job_id="",
    status="ignored_live",
)
```

If metadata lookup raises `FetcherError`, retain the existing durable-job path
instead of turning a temporary network failure into an ignored video. For an
existing `ignored_live` row, `retry_video()` returns HTTP 409 and never queues
a job.

- [ ] **Step 4: Write the failing frontend test**

Mock `summarizeVideo()` to resolve with `status: "ignored_live"` and assert the
page shows the non-error message `“已忽略直播或预约直播，不会创建总结任务。”`.

- [ ] **Step 5: Implement the response and notification**

In the submit handler, branch before the generic success notification:

```tsx
const response = await summarizeVideo(payload);
if (response.status === "ignored_live") {
  message.info("已忽略直播或预约直播，不会创建总结任务。");
  return;
}
message.success("已提交，后台处理中。");
```

- [ ] **Step 6: Run focused backend and frontend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_youtube_api.py::test_manual_upcoming_live_video_is_ignored -v
cd ../frontend && npm run test -- YouTubeHubPage.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/youtube.py backend/app/schemas/youtube.py backend/tests/test_youtube_api.py frontend/src/pages/YouTubeHubPage.tsx frontend/src/pages/YouTubeHubPage.test.tsx frontend/src/services/youtubeApi.ts
git commit -m "feat: ignore manual live video submissions"
```

### Task 4: Reclassify old live failures and keep them out of history/retries

**Files:**
- Create: `backend/alembic/versions/202607230001_ignore_live_video_rows.py`
- Modify: `backend/app/services/youtube/auto_retry.py:67-100`
- Modify: `backend/app/api/v1/youtube.py:775-930, 972-1005`
- Modify: `backend/tests/test_youtube_auto_retry.py`
- Modify: `backend/tests/test_youtube_api.py`

- [ ] **Step 1: Write failing retry/history tests**

Add an existing row with `fetch_status="ignored_live"` and assert both
behaviors:

```python
def test_auto_retry_skips_ignored_live_video(session: Session) -> None:
    _add_video(session, video_id="live123", fetch_status="ignored_live")

    report = FailedVideoRetryScanner(session, orchestrator, settings).scan()

    assert report.retried == 0
    assert orchestrator.calls == []

def test_summary_history_excludes_ignored_live_video(client: TestClient, db_session: Session) -> None:
    _add_video(db_session, video_id="live123", fetch_status="ignored_live")

    response = client.get("/api/v1/youtube/summaries?workspace_id=ws_default")

    assert "live123" not in {item["video_id"] for item in response.json()}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_youtube_auto_retry.py::test_auto_retry_skips_ignored_live_video \
  tests/test_youtube_api.py::test_summary_history_excludes_ignored_live_video -v
```

Expected: history test FAILS because the current list query includes every
video row. The retry test documents the terminal-state contract.

- [ ] **Step 3: Add the data migration and terminal-state exclusions**

Create an Alembic data migration that updates only historical failures whose
error text matches yt-dlp's scheduled/live broadcast reasons:

```python
op.execute(
    """
    UPDATE video
    SET fetch_status = 'ignored_live',
        error_message = 'ignored live broadcast'
    WHERE fetch_status = 'failed'
      AND (
        lower(error_message) LIKE '%this live event will begin%'
        OR lower(error_message) LIKE '%this live event is scheduled%'
        OR lower(error_message) LIKE '%this live event is currently live%'
      )
    """
)
```

Exclude `ignored_live` in `list_summaries()` with
`Video.fetch_status != "ignored_live"`, keep it outside the auto-retry
candidate query, and reject `retry_video()` with an HTTP 409 response. Do not
delete pre-existing documents.

- [ ] **Step 4: Run focused tests to verify they pass**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/202607230001_ignore_live_video_rows.py backend/app/services/youtube/auto_retry.py backend/app/api/v1/youtube.py backend/tests/test_youtube_auto_retry.py backend/tests/test_youtube_api.py
git commit -m "fix: exclude live broadcasts from YouTube history"
```

### Task 5: Run complete verification and document the behavior

**Files:**
- Modify: `README.md` (YouTube behavior note)

- [ ] **Step 1: Document the exclusion rule**

Add one concise README sentence: `Scheduled and currently live YouTube
broadcasts are ignored; completed livestream replays are processed normally.`

- [ ] **Step 2: Run backend verification**

Run:

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

Expected: all tests and Ruff pass.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: all tests, lint, and production build pass.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md
git commit -m "docs: describe live broadcast exclusion"
```
