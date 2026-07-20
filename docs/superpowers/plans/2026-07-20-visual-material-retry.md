# 视觉资料保护与人工重试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve automatic YouTube visual evidence, allow explicit visual-only retries, and retry transient YouTube REST failures.

**Architecture:** Automatic analysis becomes read-preserving. A dedicated `visual_analysis_retry` task is the sole replacement path. The existing task worker owns state while the video page polls it. The REST fetcher owns bounded transient-error retries.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, task_job worker, urllib, React, TypeScript, Ant Design, pytest, Vitest.

---

### Task 1: Preserve automatic visual evidence

**Files:**
- Modify: `backend/app/services/youtube/visual_analysis.py`
- Test: `backend/tests/test_youtube_visual_analysis.py`

- [ ] Write a failing test that creates a video with one persisted frame, runs `service.analyze(video, video.video_id)` with a fake extractor/OCR that returns `[]`, then asserts the old frame id remains.
- [ ] Run `cd backend && .venv/bin/python -m pytest tests/test_youtube_visual_analysis.py -v`; expect failure because `_persist` deletes existing rows.
- [ ] Add `replace_existing: bool = False` to `VideoVisualAnalysisService.analyze`. If the video already has persisted frames and replacement is false, return `load_frame_results`. When a new result list is empty, do not call `_persist` and do not replace the image directory. In replacement mode only, replace rows and directories after a non-empty result is fully prepared.
- [ ] Run the full visual-analysis test module and commit with `fix: preserve automatic visual evidence`.

### Task 2: Add the visual-only retry task and API

**Files:**
- Modify: `backend/app/services/youtube/summary_job_handler.py`
- Modify: `backend/app/api/v1/youtube.py`
- Modify: `backend/app/schemas/youtube.py`
- Test: `backend/tests/test_youtube_visual_retry.py`

- [ ] Write a failing API test: two POSTs to `/youtube/videos/{video_id}/visual-analysis/retry` return status 202 and the same active job id with `job_type="visual_analysis_retry"`.
- [ ] Run `cd backend && .venv/bin/python -m pytest tests/test_youtube_visual_retry.py -v`; expect endpoint-not-found failure.
- [ ] Define `VISUAL_ANALYSIS_RETRY_JOB_TYPE = "visual_analysis_retry"`. Its handler loads `Video` from `job.target_id`, builds the visual service, calls `analyze(video, video.video_id, replace_existing=True)`, and raises `RuntimeError("visual retry produced no usable frames; existing evidence was preserved")` on an empty result. On success return `{"video_id": video.id, "frame_count": len(frames)}`.
- [ ] Register the handler; add POST enqueue and GET status endpoints. Responses expose id, job type, status, progress, output, and error, never credentials.
- [ ] Verify duplicate click reuse, success replacement, and empty-result preservation; commit with `feat: add visual analysis retry jobs`.

### Task 3: Retry transient YouTube REST failures

**Files:**
- Modify: `backend/app/services/youtube/fetcher.py`
- Test: `backend/tests/test_youtube_fetcher_retry.py`

- [ ] Write a failing test with an injected opener that first raises `URLError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF")` and then returns `{"items": []}`; assert `_get("videos", {"part": "snippet"})` succeeds after two calls.
- [ ] Run `cd backend && .venv/bin/python -m pytest tests/test_youtube_fetcher_retry.py -v`; expect failure because `_get` attempts once.
- [ ] Add `is_transient_youtube_api_error` for TLS EOF, reset, timeout, HTTP 429 and 5xx. Inject opener and sleep dependencies. Retry at most three total attempts with 0.5s then 1.0s delay; 400/401/403/404 make one attempt only. Error logs must not include the API key.
- [ ] Run the retry and existing fetch-chain tests; commit with `fix: retry transient YouTube API failures`.

### Task 4: Add front-end retry status

**Files:**
- Modify: `frontend/src/services/youtubeApi.ts`
- Modify: `frontend/src/pages/VideoSummaryPage.tsx`
- Test: `frontend/src/pages/VideoSummaryPage.test.tsx`

- [ ] Write a failing video-page test that clicks `重试生成`, sees `视觉资料生成中`, advances a mocked status response to succeeded, and asserts the refreshed card includes an image.
- [ ] Run `cd frontend && npm run test -- src/pages/VideoSummaryPage.test.tsx`; expect failure because no retry UI exists.
- [ ] Add typed retry/status API clients. Render the same button in populated and empty visual tabs. Poll each three seconds while pending/running. On success reload the summary card; on failure display `旧视觉资料已保留：<message>` and re-enable the button.
- [ ] Run video-page tests and commit with `feat: add visual analysis retry control`.

### Task 5: Document and verify

**Files:**
- Modify: `README.md`

- [ ] Document that automatic work preserves old visual evidence and only successful “重试生成” replaces it.
- [ ] Run `cd backend && .venv/bin/python -m pytest && .venv/bin/ruff check .`; expect all backend tests and Ruff pass.
- [ ] Run `cd frontend && npm run test && npm run lint && npm run build`; expect all tests, lint, and build pass.
- [ ] Inspect the diff for secret leakage, then commit with `docs: explain visual evidence retry behavior`.
