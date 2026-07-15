# Content Chinese Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make newly collected and existing YouTube, investment, and macro-calendar content reliably produce Chinese reading fields while preserving original evidence.

**Architecture:** Keep original source text unchanged and add/repair Chinese derived fields. Force YouTube structured summaries to output Simplified Chinese at prompt level, keep transcript translation as a quality boost, and add backfill/retry paths for investment and macro items that still lack `title_zh` or `summary_zh`.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic v2, existing `TaskJob` worker, existing OpenAI-compatible structured-output client, React + TypeScript + Vite + Ant Design.

---

## File Map

- Modify `backend/app/services/youtube/summary.py`: force all summary, chunk, merge, and mindmap prompts to produce Simplified Chinese.
- Modify `backend/app/services/youtube/orchestrator.py`: record transcript translation warnings in `Document.metadata_` / `Video.metadata_` when translation falls back to source.
- Modify `backend/app/services/youtube/translation.py`: expose a translation result warning without changing the public transcript shape.
- Modify `backend/tests/test_translation.py`: cover the new `TranslationService.last_warning` behavior on translation fallback.
- Modify `backend/tests/test_map_reduce.py`: assert chunk and merge prompts require Simplified Chinese.
- Modify `backend/tests/test_youtube_orchestrator.py`: assert translation fallback records metadata and still summarizes with Chinese-output prompt.
- Modify `backend/app/services/investment/translation.py`: process recent untranslated items first and expose a bounded backfill helper.
- Modify `backend/scripts/backfill_investment_translations.py`: add a CLI for translating existing investment/macro items.
- Modify `backend/tests/test_investment_translation.py`: cover recency ordering and backfill behavior.
- Modify `backend/tests/test_investment_backfill_scripts.py`: cover the new script.
- Modify `frontend/src/pages/InvestmentItemsPage.tsx`, `frontend/src/pages/InvestmentCalendarPage.tsx`, `frontend/src/components/investment/InvestmentItemDrawer.tsx`: show a visible `待翻译` tag when Chinese fields are missing.
- Modify related frontend tests: `InvestmentItemsPage.test.tsx` and `InvestmentDashboardPage.test.tsx`; add `InvestmentCalendarPage.test.tsx` only when the page already has an adjacent test harness after inspection.
- Remote deployment config: update production `.env` to `TRANSLATE_TO_CHINESE=true` during deployment; do not commit secrets.

## Task 1: Force YouTube Summary Output To Chinese

**Files:**
- Modify: `backend/app/services/youtube/summary.py`
- Test: `backend/tests/test_map_reduce.py`

- [ ] **Step 1: Write failing prompt tests**

Add tests that assert every YouTube summary prompt requires Simplified Chinese output.

```python
def test_single_summary_prompt_requires_simplified_chinese() -> None:
    transcript = _transcript([("hello world", 0, 5)])
    prompt = build_summary_prompt("English title", transcript, chapters=[])
    assert "最终输出必须使用简体中文" in prompt
    assert "不要跟随字幕语言输出英文" in prompt


def test_chunk_and_merge_prompts_require_simplified_chinese() -> None:
    transcript = _transcript([("hello world", 0, 5), ("more content", 10, 5)])
    chunk = VideoChunk(index=0, start_sec=0, end_sec=30, content="hello world")
    chunk_prompt = build_chunk_summary_prompt("English title", chunk, transcript)
    assert "最终输出必须使用简体中文" in chunk_prompt

    chunk_summary = ChunkSummary(
        section_summary="English section",
        key_points=[KeyPoint(point="English point", timestamp=0, timestamp_str="00:00")],
    )
    merge_prompt = build_merge_prompt(
        "English title",
        [chunk_summary],
        chapters=[],
        transcript_source="manual",
        visual_frames=None,
    )
    assert "最终输出必须使用简体中文" in merge_prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_map_reduce.py::test_single_summary_prompt_requires_simplified_chinese tests/test_map_reduce.py::test_chunk_and_merge_prompts_require_simplified_chinese -q
```

Expected: both tests fail because the current prompt says to use the same language as the transcript.

- [ ] **Step 3: Implement Chinese-output prompt contract**

Replace `_SUMMARY_SYSTEM_HINT` in `backend/app/services/youtube/summary.py` with a Chinese-output contract:

```python
_SUMMARY_SYSTEM_HINT = (
    "你是一个面向中文投资研究工作流的视频总结助手。"
    "无论字幕、标题、视觉资料或章节是什么语言，最终输出必须使用简体中文。"
    "不要跟随字幕语言输出英文；保留必要的公司名、产品名、股票代码和专有名词原文。"
    "所有 SummaryResult、ChunkSummary、MindmapData 字段中的自然语言内容都要中文化。"
)
```

Update `build_summary_prompt`, `build_chunk_summary_prompt`, and `build_merge_prompt` final instructions to repeat:

```python
"最终输出必须使用简体中文。不要输出英文总结。"
```

Do not translate the transcript text itself in the prompt; only change the model instructions.

- [ ] **Step 4: Run focused tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_map_reduce.py -q
```

Expected: all map-reduce tests pass.

## Task 2: Record YouTube Transcript Translation Fallbacks

**Files:**
- Modify: `backend/app/services/youtube/translation.py`
- Modify: `backend/app/services/youtube/orchestrator.py`
- Test: `backend/tests/test_youtube_orchestrator.py`

- [ ] **Step 1: Write failing orchestrator test**

Add a test with a translation service that returns the original English transcript and exposes a warning. The summary still succeeds, and the created document metadata records the warning.

```python
class WarningTranslationService:
    last_warning = "translation batch failed; keeping source text"

    def translate(self, transcript: Transcript, *, enabled: bool = True) -> Transcript:
        return transcript


def test_youtube_translation_warning_is_recorded(session: Session) -> None:
    extractor = FakeTranscriptExtractor().with_transcript("dQw4w9WgXcQ", _transcript())
    service = SummaryService(MockStructuredOutputClient())
    orchestrator = VideoSummaryOrchestrator(
        session=session,
        fetcher=FakeYouTubeFetcher(),
        transcript_extractor=extractor,
        summary_service=service,
        translation_service=WarningTranslationService(),
        translate_enabled=True,
    )

    result = orchestrator.summarize_url(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        workspace_id="ws_default",
    )

    assert result.succeeded
    document = session.get(Document, result.document_id)
    assert document is not None
    assert document.metadata_["translation_warning"] == "translation batch failed; keeping source text"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_youtube_orchestrator.py::test_youtube_translation_warning_is_recorded -q
```

Expected: fails because no translation warning is persisted.

- [ ] **Step 3: Implement warning propagation**

In `backend/app/services/youtube/translation.py`, add an instance attribute:

```python
class TranslationService:
    def __init__(self, llm_client: StructuredOutputClient) -> None:
        self.llm_client = llm_client
        self.last_warning: str | None = None
```

Reset it at the start of `translate`:

```python
self.last_warning = None
```

When the whole translation fails:

```python
self.last_warning = f"translation failed: {exc}"
return transcript
```

When all batches fall back:

```python
if not any_translated:
    self.last_warning = "translation produced no Chinese batches; source transcript kept"
```

In `backend/app/services/youtube/orchestrator.py`, after `translation_service.translate(...)`, capture:

```python
translation_warning = getattr(self.translation_service, "last_warning", None)
```

Pass `translation_warning` into `_persist_document(...)` or set it immediately after document creation:

```python
if translation_warning:
    metadata = dict(document.metadata_ or {})
    metadata["translation_warning"] = translation_warning
    metadata["summary_language"] = "zh"
    document.metadata_ = metadata
    video_metadata = dict(video.metadata_ or {})
    video_metadata["translation_warning"] = translation_warning
    video.metadata_ = video_metadata
    self.session.commit()
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_translation.py tests/test_youtube_orchestrator.py -q
```

Expected: tests pass.

## Task 3: Add Investment/Macro Backfill Translation Script

**Files:**
- Modify: `backend/app/services/investment/translation.py`
- Add: `backend/scripts/backfill_investment_translations.py`
- Modify: `backend/tests/test_investment_translation.py`
- Modify: `backend/tests/test_investment_backfill_scripts.py`

- [ ] **Step 1: Write failing service test for newest-first backfill**

Add a test that creates two untranslated macro items and asserts the newest item is translated first when `limit=1`.

```python
def test_translation_backfill_processes_newest_items_first(session: Session) -> None:
    older = InvestmentItem(
        id="inv_old_macro",
        workspace_id="ws_default",
        dedupe_key="old",
        title="Older Fed item",
        summary="Older summary",
        info_layer="macro_calendar",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    newer = InvestmentItem(
        id="inv_new_macro",
        workspace_id="ws_default",
        dedupe_key="new",
        title="Newer Fed item",
        summary="Newer summary",
        info_layer="macro_calendar",
        published_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    session.add_all([older, newer])
    session.commit()

    service = InvestmentTranslationService(session, llm_client=_translation_llm({
        "inv_new_macro": ("新的美联储条目", "新的摘要"),
    }))

    result = service.translate_untranslated(limit=1)

    assert result["translated"] == 1
    assert session.get(InvestmentItem, "inv_new_macro").title_zh == "新的美联储条目"
    assert session.get(InvestmentItem, "inv_old_macro").title_zh is None
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_investment_translation.py::test_translation_backfill_processes_newest_items_first -q
```

Expected: fails because translation currently orders by `created_at` ascending.

- [ ] **Step 3: Implement newest-first selection**

In `InvestmentTranslationService.translate_untranslated`, change ordering:

```python
.order_by(InvestmentItem.published_at.desc().nullslast(), InvestmentItem.created_at.desc())
```

Keep existing filters and limits.

- [ ] **Step 4: Add backfill script**

Create `backend/scripts/backfill_investment_translations.py`:

```python
from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.infrastructure.database import SessionLocal
from app.services.investment.translation import InvestmentTranslationService
from app.services.research_dependencies import build_llm_client_from_settings


def run_backfill(
    *,
    workspace_id: str = "ws_default",
    limit: int = 50,
    batches: int = 1,
) -> dict[str, int]:
    translated = 0
    skipped = 0
    session = SessionLocal()
    try:
        service = InvestmentTranslationService(
            session=session,
            llm_client=build_llm_client_from_settings(),
        )
        for _ in range(batches):
            result = service.translate_untranslated(
                workspace_id=workspace_id,
                limit=limit,
                raise_on_failure=True,
            )
            translated += result["translated"]
            skipped += result["skipped"]
            if result["translated"] == 0 and result["skipped"] == 0:
                break
        return {"translated": translated, "skipped": skipped}
    finally:
        session.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Chinese translations for investment items.")
    parser.add_argument("--workspace-id", default="ws_default")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--batches", type=int, default=1)
    args = parser.parse_args(argv)
    result = run_backfill(
        workspace_id=args.workspace_id,
        limit=args.limit,
        batches=args.batches,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Add script test**

In `backend/tests/test_investment_backfill_scripts.py`, add:

```python
def test_backfill_investment_translations_script_imports() -> None:
    from backend.scripts.backfill_investment_translations import main, run_backfill

    assert callable(main)
    assert callable(run_backfill)
```

Use the repository's existing script import style:

```python
from scripts.backfill_investment_translations import main, run_backfill
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_investment_translation.py tests/test_investment_backfill_scripts.py -q
```

Expected: tests pass.

## Task 4: Show Visible Pending-Translation State In Investment UI

**Files:**
- Modify: `frontend/src/pages/InvestmentItemsPage.tsx`
- Modify: `frontend/src/pages/InvestmentCalendarPage.tsx`
- Modify: `frontend/src/components/investment/InvestmentItemDrawer.tsx`
- Test: `frontend/src/pages/InvestmentItemsPage.test.tsx`

- [ ] **Step 1: Write failing frontend test**

In `InvestmentItemsPage.test.tsx`, add an API item with English `title` and `summary`, but null `title_zh` and `summary_zh`, then assert the page shows `待翻译`.

```tsx
expect(await screen.findByText("待翻译")).toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd frontend
npm run test -- InvestmentItemsPage.test.tsx --run
```

Expected: fails because missing Chinese fields are currently silent.

- [ ] **Step 3: Add a local helper**

In pages/components that display `InvestmentItem`, add:

```tsx
function needsTranslation(item: InvestmentItem) {
  return !item.title_zh || Boolean(item.summary && !item.summary_zh);
}
```

Use `<Tag color="orange">待翻译</Tag>` next to titles when this returns true.

- [ ] **Step 4: Update item list and drawer**

In `InvestmentItemsPage.tsx`, render:

```tsx
<Space>
  <span>{r.title_zh ?? r.title}</span>
  {needsTranslation(r) && <Tag color="orange">待翻译</Tag>}
</Space>
```

In `InvestmentItemDrawer.tsx`, render the same tag in the drawer title. Keep the original English fallback visible until backfill completes.

- [ ] **Step 5: Update calendar page**

In `InvestmentCalendarPage.tsx`, render `待翻译` beside macro calendar items lacking Chinese fields.

- [ ] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend
npm run test -- InvestmentItemsPage.test.tsx --run
```

Expected: tests pass.

## Task 5: Add YouTube Existing-English Detection Utility

**Files:**
- Modify: `backend/app/services/youtube/summary_retry.py` or add `backend/app/services/youtube/localization.py`
- Test: `backend/tests/test_youtube_summary_localization.py`

- [ ] **Step 1: Write failing utility tests**

Create tests for simple language detection:

```python
def test_summary_needs_chinese_localization_when_tldr_is_english() -> None:
    assert needs_chinese_localization({
        "tldr": "The recent selloff in semiconductor stocks was driven by macro pressure.",
        "tags": ["Tech Stocks", "AI Infrastructure"],
    }) is True


def test_summary_does_not_need_chinese_localization_when_tldr_is_chinese() -> None:
    assert needs_chinese_localization({
        "tldr": "本期视频分析了半导体股票下跌的主要原因。",
        "tags": ["半导体", "AI 基础设施"],
    }) is False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_youtube_summary_localization.py -q
```

Expected: import/function missing.

- [ ] **Step 3: Implement utility**

Create `backend/app/services/youtube/localization.py`:

```python
from __future__ import annotations

import re
from typing import Any

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def needs_chinese_localization(summary_json: dict[str, Any] | None) -> bool:
    if not summary_json:
        return False
    text_parts: list[str] = []
    tldr = summary_json.get("tldr")
    if isinstance(tldr, str):
        text_parts.append(tldr)
    for tag in summary_json.get("tags") or []:
        if isinstance(tag, str):
            text_parts.append(tag)
    for point in summary_json.get("key_points") or []:
        if isinstance(point, dict) and isinstance(point.get("point"), str):
            text_parts.append(point["point"])
    text = " ".join(text_parts)
    if not text.strip():
        return False
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    return latin > 40 and cjk * 2 < latin
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_youtube_summary_localization.py -q
```

Expected: tests pass.

## Task 6: Production Config And Backfill Deployment

**Files:**
- No committed secret/config file changes.
- Remote: `/home/yi5an/knowpilot/.env`
- Remote command: `docker compose -f docker-compose.prod.yml up -d --no-build --force-recreate backend frontend`

- [ ] **Step 1: Verify local tests before deployment**

Run:

```bash
cd backend
.venv/bin/python -m ruff check app tests
.venv/bin/python -m pytest tests/test_translation.py tests/test_map_reduce.py tests/test_youtube_orchestrator.py tests/test_investment_translation.py tests/test_investment_backfill_scripts.py tests/test_investment_api.py -q

cd ../frontend
npm run test -- InvestmentItemsPage.test.tsx InvestmentDashboardPage.test.tsx InvestmentDigestPage.test.tsx VideoSummaryPage.test.tsx --run
npm run lint
npm run build
```

Expected: all pass. Vite chunk-size warnings are acceptable.

- [ ] **Step 2: Deploy code to remote**

Use rsync to copy source files while preserving `.env`, database files, virtualenvs, dependency folders, and local storage.

```bash
rsync -az --exclude='.git/' --exclude='.env' --exclude='.env.*' --exclude='.DS_Store' \
  --exclude='node_modules/' --exclude='frontend/node_modules/' --exclude='frontend/dist/' \
  --exclude='backend/.venv/' --exclude='backend/knowpilot.db' --exclude='backend/knowpilot.db-*' \
  -e 'ssh -p 12222' /Users/domi/ZCodeProject/my_knowlage/ \
  yi5an@123.57.165.38:/home/yi5an/knowpilot/
```

- [ ] **Step 3: Set production translation config**

On remote, update `.env` without printing secrets:

```bash
cd /home/yi5an/knowpilot
cp .env ".env.bak-translate-$(date +%Y%m%d%H%M%S)"
python3 - <<'PY'
from pathlib import Path
path = Path(".env")
lines = path.read_text().splitlines()
out = []
seen = False
for line in lines:
    if line.startswith("TRANSLATE_TO_CHINESE="):
        out.append("TRANSLATE_TO_CHINESE=true")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append("TRANSLATE_TO_CHINESE=true")
path.write_text("\n".join(out) + "\n")
PY
```

- [ ] **Step 4: Rebuild/restart remote services**

Use normal compose if Docker Hub is healthy; otherwise use the existing hotfix Dockerfile strategy.

```bash
cd /home/yi5an/knowpilot
docker compose -f docker-compose.prod.yml up -d --build backend frontend
```

If Docker Hub EOF occurs, build from existing images:

```bash
printf "%s\n" \
  "FROM knowpilot-backend:latest" \
  "WORKDIR /app" \
  "COPY app ./app" \
  "COPY alembic ./alembic" \
  "COPY alembic.ini ./alembic.ini" \
  "COPY scripts ./scripts" \
  "RUN chmod +x scripts/start_prod.sh" \
  > backend/Dockerfile.hotfix
docker build -f backend/Dockerfile.hotfix -t knowpilot-backend:latest ./backend
docker compose -f docker-compose.prod.yml up -d --no-build --force-recreate backend
```

- [ ] **Step 5: Run investment translation backfill**

On remote:

```bash
docker exec knowpilot-backend python -m scripts.backfill_investment_translations --workspace-id ws_default --limit 20 --batches 5
```

Expected: output includes a `translated` count or cleanly reports zero remaining.

- [ ] **Step 6: Verify remote**

Run:

```bash
curl -fsS http://123.57.165.38:13080/api/v1/health
curl -fsS http://123.57.165.38:13080/api/v1/investment/dashboard
curl -fsS 'http://123.57.165.38:13080/api/v1/investment/macro-events?limit=5'
```

Expected:
- health returns `{"status":"ok"}`;
- dashboard `untranslated_count` decreases after backfill;
- recent macro items include `title_zh` / `summary_zh` where translation succeeded.

## Final Verification

- [ ] Run backend focused tests:

```bash
cd backend
.venv/bin/python -m pytest tests/test_translation.py tests/test_map_reduce.py tests/test_youtube_orchestrator.py tests/test_investment_translation.py tests/test_investment_backfill_scripts.py tests/test_investment_api.py -q
```

- [ ] Run backend lint:

```bash
cd backend
.venv/bin/python -m ruff check app tests
```

- [ ] Run frontend tests/lint/build:

```bash
cd frontend
npm run test -- InvestmentItemsPage.test.tsx InvestmentDashboardPage.test.tsx InvestmentDigestPage.test.tsx VideoSummaryPage.test.tsx --run
npm run lint
npm run build
```

- [ ] Verify public URL:

```bash
curl -fsS http://123.57.165.38:13080/api/v1/health
```

## Rollback Notes

- Remote `.env` backup is created before changing `TRANSLATE_TO_CHINESE`.
- Code deployment preserves `.env` and database files.
- If backend fails to boot, restore the previous remote code backup or re-tag the prior `knowpilot-backend` image if available.
