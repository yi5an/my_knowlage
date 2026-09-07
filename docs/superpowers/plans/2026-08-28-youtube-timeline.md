# YouTube History Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Replace the fixed 50-item YouTube history list with a cursor-paginated, all-status blogger swimlane timeline ordered by YouTube publication time.

**Architecture:** Keep Video and Document as the source of truth. Add a pure timeline query/service that computes effective timestamps, stable opaque cursors, lane/month metadata, and status counts. Expose it through a new endpoint while preserving the existing summaries endpoint. Add a focused React component that consumes pages and groups cards into lanes.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, pytest; React, TypeScript, Ant Design, Vitest/Testing Library.

---

## File map

- Create backend/app/schemas/youtube_timeline.py for timeline response schemas and cursor contracts.
- Create backend/app/services/youtube/timeline.py for timestamp normalization, cursor logic, SQL query, status mapping, and metadata.
- Modify backend/app/api/v1/youtube.py to expose GET /youtube/timeline without changing existing routes.
- Create backend/tests/test_youtube_timeline.py for SQLite service and API tests.
- Modify frontend/src/services/youtubeApi.ts with timeline types and getYouTubeTimeline.
- Create frontend/src/components/youtube/YouTubeTimeline.tsx for lanes, sticky headers, filters, and infinite loading.
- Create frontend/src/components/youtube/YouTubeTimeline.test.tsx for component behavior.
- Modify frontend/src/pages/YouTubeHubPage.tsx and its tests to replace the fixed 50-item history section.

### Task 1: Define schemas and cursor rules

**Files:** backend/app/schemas/youtube_timeline.py; backend/tests/test_youtube_timeline.py

- [ ] Write failing tests for cursor round-trip, invalid cursor rejection, and Pydantic field validation.

    def test_cursor_round_trip_preserves_timestamp_and_video_id() -> None:
        token = encode_cursor(datetime(2026, 8, 28, tzinfo=UTC), "video_b")
        assert decode_cursor(token) == (datetime(2026, 8, 28, tzinfo=UTC), "video_b")

    def test_invalid_cursor_raises_value_error() -> None:
        with pytest.raises(ValueError):
            decode_cursor("not-a-cursor")

- [ ] Run cd backend && uv run pytest -q tests/test_youtube_timeline.py. Expected: collection fails because the module does not exist.
- [ ] Implement TimelineItem, TimelineChannel, TimelineMonth, and TimelinePage. TimelineItem.time_source must be published_at or created_at; next_cursor is nullable.
- [ ] Implement URL-safe base64 over compact JSON containing effective_time and video_id. Reject malformed JSON, missing fields, naive timestamps, and invalid timestamps with ValueError. Never encode database IDs or secrets.
- [ ] Run the focused tests again; expected: PASS.
- [ ] Commit with git add backend/app/schemas/youtube_timeline.py backend/tests/test_youtube_timeline.py && git commit -m "feat: define YouTube timeline schemas".

### Task 2: Implement the backend query service

**Files:** backend/app/services/youtube/timeline.py (create); backend/tests/test_youtube_timeline.py

- [ ] Seed tests with published and missing publication dates, equal timestamps, multiple channels, completed/processing/failed/access-denied/live statuses. Assert:

    page = query_timeline(session, workspace_id="ws_default", limit=2)
    assert [item.video_id for item in page.items] == ["newer", "same-a"]
    assert page.items[1].time_source == "published_at"
    assert page.next_cursor is not None
    next_page = query_timeline(session, workspace_id="ws_default", limit=2, cursor=page.next_cursor)
    assert {item.video_id for item in page.items}.isdisjoint(item.video_id for item in next_page.items)

- [ ] Run the focused test; expected: FAIL because query_timeline is absent.
- [ ] Implement query_timeline(session, workspace_id, *, limit, cursor=None, channel_id=None, status=None, year_month=None) -> TimelinePage:
  1. Outer-join Video to Document, scope to workspace, and exclude ignored_live.
  2. Use published_at or created_at, normalized to UTC, and expose time_source.
  3. Apply channel, status, and YYYY-MM filters before cursor filtering.
  4. Sort by effective_time DESC, video_id DESC; fetch limit + 1 rows and encode the last returned key.
  5. Map existing summary fields, with title fallback to video_id and unknown channel fallback to 未识别博主.
  6. Return channels ordered by latest effective time, month counts, total, and status counts. access_denied is returned but retryable is false.
  7. Validate limit 1..100 and raise TimelineQueryError for invalid cursors or malformed year_month.
- [ ] Run pytest and ruff check on the new files; expected: PASS and no lint errors.
- [ ] Commit with git add backend/app/services/youtube/timeline.py backend/tests/test_youtube_timeline.py && git commit -m "feat: add cursor-paginated YouTube timeline query".

### Task 3: Expose the API

**Files:** backend/app/api/v1/youtube.py; backend/tests/test_youtube_timeline.py

- [ ] Add endpoint tests for default parameters, cursor continuation, channel_id, status, year_month, malformed cursor (400), and live exclusion. Expected before implementation: 404.
- [ ] Add GET /api/v1/youtube/timeline with typed query parameters workspace_id=ws_default, limit=50, cursor, channel_id, status, year_month. Delegate to query_timeline and map TimelineQueryError to the standard HTTP 400 error. Leave summaries, retry, subscriptions, and live-ignore routes unchanged.
- [ ] Run cd backend && uv run pytest -q tests/test_youtube_timeline.py tests/test_youtube_api.py. Expected: PASS.
- [ ] Commit with git add backend/app/api/v1/youtube.py backend/tests/test_youtube_timeline.py && git commit -m "feat: expose YouTube timeline API".

### Task 4: Build the frontend timeline

**Files:** frontend/src/services/youtubeApi.ts; frontend/src/components/youtube/YouTubeTimeline.tsx; frontend/src/components/youtube/YouTubeTimeline.test.tsx

- [ ] Write failing tests that mock getYouTubeTimeline and assert six active lanes by default, the 显示全部博主 control, all statuses, next_cursor loading, filter reset, and failed-card retry.
- [ ] Run cd frontend && npm test -- --run src/components/youtube/YouTubeTimeline.test.tsx. Expected: FAIL because the component/API function is absent.
- [ ] Add TimelineItem, TimelineChannel, TimelineMonth, and TimelinePage TypeScript types plus getYouTubeTimeline(params) using URLSearchParams and apiRequest. Omit null query values.
- [ ] Implement local page state with video_id deduplication; group by normalized channel; sort lanes by latest effective time; show six lanes until expanded; keep the date column and lane headers sticky; use a horizontally scrollable container; observe a bottom sentinel for older pages; retain existing detail/retry actions; keep loaded content when a later page fails.
- [ ] Run the component test and npm run build; expected: PASS and successful build.
- [ ] Commit with git add frontend/src/services/youtubeApi.ts frontend/src/components/youtube/YouTubeTimeline.tsx frontend/src/components/youtube/YouTubeTimeline.test.tsx && git commit -m "feat: add YouTube blogger swimlane timeline".

### Task 5: Integrate with the YouTube hub

**Files:** frontend/src/pages/YouTubeHubPage.tsx; frontend/src/pages/YouTubeHubPage.test.tsx

- [ ] Add integration assertions that manual submission, subscription navigation, detail links, filters, and retry remain available while history requests /youtube/timeline rather than hard-coding limit=50.
- [ ] Replace fixed listSummaries history state with YouTubeTimeline. Keep manual submission and subscription controls unchanged. Preserve inline initial-load error handling.
- [ ] Run npm test -- --run src/pages/YouTubeHubPage.test.tsx src/components/youtube/YouTubeTimeline.test.tsx, npm run lint, and npm run build; expected: all pass.
- [ ] Commit with git add frontend/src/pages/YouTubeHubPage.tsx frontend/src/pages/YouTubeHubPage.test.tsx && git commit -m "feat: integrate YouTube history timeline".

### Task 6: Full verification and handoff

**Files:** README.md only if user-facing timeline usage needs documentation.

- [ ] Run backend uv run pytest, ruff check ., and mypy app. Use the Python 3.12 backend container if local dependencies are unavailable and record that limitation.
- [ ] Run frontend npm test -- --run, npm run lint, and npm run build.
- [ ] Manually verify default six lanes, 显示全部博主, horizontal scrolling, sticky date/header, older-page loading, year/month jump, all statuses, failed retry, and no live cards.
- [ ] Run git status --short and git log --oneline -6. If README changed, commit it with docs: describe YouTube history timeline.

## Self-review checklist

- All-status display, live exclusion, publication-time fallback, stable cursor pagination, month/channel navigation, six-lane default, expand-all scrolling, sticky columns, infinite loading, retry, and regression coverage are assigned to Tasks 1–6.
- Existing summary, retry, subscription, detail, Cookie, and live-ignore behavior remains compatible.
- No migration, secret change, or destructive data operation is required.
