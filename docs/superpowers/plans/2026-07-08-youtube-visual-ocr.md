# YouTube Visual OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract useful PPT, mind map, chart, table, and dense on-screen text from YouTube videos and include it as visual evidence in summaries.

**Architecture:** Add a backend visual-analysis service that samples frames with `yt-dlp` + `ffmpeg`, deduplicates visually similar frames, calls an internal OCR HTTP service, persists frame analyses, and passes compact visual notes into the existing summary prompt. Keep OCR behind an HTTP client so PaddleOCR can be deployed locally without coupling application code to Paddle internals.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2, ffmpeg, yt-dlp, Pillow/imagehash for local frame hashing, React/TypeScript/Ant Design.

---

### Task 1: Data Contracts and Storage

**Files:**
- Modify: `backend/app/schemas/youtube.py`
- Modify: `backend/app/infrastructure/models.py`
- Create: `backend/alembic/versions/202607080001_video_frame_analysis.py`
- Test: `backend/tests/test_youtube_data_models.py`

- [ ] Add `OcrBlock`, `VideoFrameAnalysisResult`, and `VideoFrameAnalysisResponse` schemas with timestamp, frame type, OCR text, structured notes, bbox blocks, confidence, and image URL/path fields.
- [ ] Add `VideoFrameAnalysis` SQLAlchemy model linked to `Video`.
- [ ] Add Alembic migration for `video_frame_analysis`.
- [ ] Add schema/model tests proving JSON fields round-trip under SQLite.

### Task 2: OCR Client and Visual Analysis Service

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/youtube/visual_analysis.py`
- Test: `backend/tests/test_youtube_visual_analysis.py`

- [ ] Add runtime dependencies `Pillow` and `imagehash`.
- [ ] Add settings for visual analysis enablement, sampling interval, max frame count, min text length, similarity threshold, OCR URL, and timeout.
- [ ] Implement `OcrClient` for `POST /ocr` multipart image upload.
- [ ] Implement frame extraction with `yt-dlp` and `ffmpeg`.
- [ ] Implement perceptual-hash deduplication and useful-text filtering.
- [ ] Implement deterministic structured notes from OCR blocks.
- [ ] Add tests with fake extractor/OCR client; no network or real video required.

### Task 3: Pipeline Integration

**Files:**
- Modify: `backend/app/services/youtube/orchestrator.py`
- Modify: `backend/app/services/youtube/summary.py`
- Modify: `backend/app/api/v1/youtube.py`
- Test: `backend/tests/test_youtube_orchestrator.py`
- Test: `backend/tests/test_youtube_api.py`

- [ ] Inject optional visual-analysis service into the orchestrator.
- [ ] Run visual analysis after metadata upsert and before summary generation.
- [ ] Persist visual frames without failing the transcript summary when visual analysis errors.
- [ ] Extend `SummaryService.summarize()` to accept compact visual notes.
- [ ] Return `visual_frames` in summary-card API responses.
- [ ] Add tests proving visual notes enter the prompt and API responses include persisted frames.

### Task 4: Frontend Rendering

**Files:**
- Modify: `frontend/src/services/youtubeApi.ts`
- Modify: `frontend/src/pages/VideoSummaryPage.tsx`
- Test: `frontend/src/pages/VideoSummaryPage.test.tsx`

- [ ] Add TypeScript types for visual frames.
- [ ] Add a `视觉资料` tab that renders frame type, timestamp, structured notes, OCR text, and image preview when present.
- [ ] Hide the tab or show an empty state when no visual frames exist.
- [ ] Add a frontend test for visual evidence rendering.

### Task 5: Deployment

**Files:**
- Modify: `docker-compose.dev.yml`
- Modify: `backend/Dockerfile.prod`
- Create: `deploy/paddleocr-service/README.md`

- [ ] Document local PaddleOCR service contract: `POST /ocr` returns OCR blocks and optional layout regions.
- [ ] Add backend image dependencies needed for Pillow/imagehash.
- [ ] Add an internal-only OCR service example for deployment.
- [ ] Deploy to the server with `OCR_BASE_URL=http://paddleocr:8866` and keep the OCR port private.

### Verification

- [ ] Run backend targeted tests: `cd backend && pytest tests/test_youtube_visual_analysis.py tests/test_youtube_orchestrator.py tests/test_youtube_api.py`.
- [ ] Run backend lint for touched code: `cd backend && ruff check app tests`.
- [ ] Run frontend tests/build: `cd frontend && npm run test -- --run VideoSummaryPage.test.tsx && npm run build`.
- [ ] On the server, verify a YouTube summary can complete when OCR is unavailable and can include frames when OCR is enabled.
