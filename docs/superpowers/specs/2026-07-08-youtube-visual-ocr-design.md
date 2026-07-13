# YouTube Visual OCR Design

## Goal

Add a local visual-capture layer for YouTube summaries so KnowPilot can extract useful information from videos that continuously show PPT slides, mind maps, charts, tables, and dense on-screen text.

## Current State

The YouTube pipeline currently uses metadata, subtitles, and ASR transcripts. It stores `thumbnail_url`, but it does not extract frames from video, run OCR on video screenshots, analyze slide layout, or merge visual evidence into the summary. The backend already ships `ffmpeg` for ASR audio processing, and the model tables have a `supports_vision` flag, but there is no active visual-analysis service.

## Recommended OCR Stack

Use a local PaddleOCR HTTP service as the first implementation:

- PP-OCRv5 for Chinese/English OCR.
- PP-StructureV3-style structured output when available.
- HTTP API boundary so KnowPilot is not tightly coupled to Paddle internals.
- JSON responses containing text, bounding boxes, confidence, reading order, and optional region type.

PaddleOCR is preferred over a simple OCR-only library because the target data is slide-like and diagram-like. Reading order and coordinates matter as much as recognized text.

## Feature Scope

The first version supports YouTube video frames only.

It will:

- Download a video preview stream with `yt-dlp` through the configured YouTube proxy.
- Extract frames with `ffmpeg`.
- Skip visually similar frames to avoid repeated slide analysis.
- Send retained frames to the local OCR service.
- Classify useful frames as `slide`, `mindmap`, `chart`, `table`, `screen_text`, or `other`.
- Store OCR text, bounding boxes, image paths, timestamps, confidence, and extracted structured notes.
- Add visual notes to the summary prompt as supplemental evidence.
- Expose visual evidence in the summary API and frontend summary page.

It will not:

- Try to reconstruct every arrow and connector in a mind map perfectly.
- Analyze ordinary talking-head frames unless they contain useful on-screen text.
- Require a cloud OCR provider.
- Replace ASR; it augments transcript-based summaries.

## Data Model

Add a `video_frame_analysis` table with:

- `id`
- `workspace_id`
- `video_id` referencing `video.id`
- `timestamp_sec`
- `timestamp_str`
- `image_path`
- `perceptual_hash`
- `frame_type`
- `ocr_text`
- `ocr_blocks`
- `structured_notes`
- `confidence`
- `created_at`

`ocr_blocks` stores line-level text with bounding boxes. `structured_notes` stores a compact Markdown/JSON-friendly representation, such as slide title, bullet points, mind map branches, chart conclusion, and table facts.

## Pipeline

Visual analysis runs after video metadata is upserted and before final summary generation:

1. Extract candidate frames at a configured interval.
2. Remove near-duplicate frames.
3. OCR each retained frame.
4. Drop frames with too little useful text.
5. Convert OCR output into structured visual notes.
6. Persist frame analyses.
7. Pass a compact visual-evidence block into summary generation.

Failures are non-fatal. If frame extraction, OCR, or visual structuring fails, the transcript summary continues and the video records a visual-analysis warning in metadata.

## Configuration

Add backend settings:

- `YOUTUBE_VISUAL_ANALYSIS_ENABLED`
- `YOUTUBE_FRAME_INTERVAL_SEC`
- `YOUTUBE_FRAME_MAX_COUNT`
- `YOUTUBE_FRAME_MIN_TEXT_CHARS`
- `YOUTUBE_FRAME_SIMILARITY_THRESHOLD`
- `OCR_BASE_URL`
- `OCR_TIMEOUT_SECONDS`

Defaults should keep the feature off until deployment has a healthy OCR service.

## API and UI

Extend the YouTube summary response with `visual_frames`.

Each item includes:

- timestamp
- frame type
- image URL or local API path
- OCR text
- structured notes
- confidence

The frontend summary page adds a `视觉资料` section for PPT, brain map, chart, table, and screen-text evidence.

## Testing

Backend tests cover:

- Frame deduplication.
- OCR client response parsing.
- Visual notes formatting for summary prompts.
- Orchestrator continues when visual analysis fails.
- Summary card API includes visual frames.

Frontend tests cover:

- Visual evidence renders when present.
- The section is hidden when no frames exist.

## Deployment

Deploy a local `paddleocr-service` container on the server and attach it to the KnowPilot Docker network. The backend calls it through `OCR_BASE_URL`, for example `http://paddleocr:8866`.

The service is internal-only by default. No OCR port should be exposed publicly.
