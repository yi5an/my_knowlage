from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

app = FastAPI(title="KnowPilot PaddleOCR Service")

_OCR_ENGINE: Any | None = None


class OcrBlock(BaseModel):
    text: str
    bbox: list[float] = Field(description="[x1, y1, x2, y2]")
    confidence: float
    reading_order: int
    region_type: str | None = None


class OcrResponse(BaseModel):
    blocks: list[OcrBlock]


def get_ocr_engine() -> Any:
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    from paddleocr import PaddleOCR

    lang = os.getenv("PADDLEOCR_LANG", "ch")
    try:
        _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=lang)
    except TypeError:
        _OCR_ENGINE = PaddleOCR(lang=lang)
    return _OCR_ENGINE


def _bbox_from_points(points: Any) -> list[float]:
    if hasattr(points, "tolist"):
        points = points.tolist()
    if not isinstance(points, list) or not points:
        return [0.0, 0.0, 0.0, 0.0]
    xs = [float(p[0]) for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
    ys = [float(p[1]) for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not xs or not ys:
        return [0.0, 0.0, 0.0, 0.0]
    return [min(xs), min(ys), max(xs), max(ys)]


def _normalise_result(raw: Any) -> list[OcrBlock]:
    blocks: list[OcrBlock] = []
    pages = raw if isinstance(raw, list) else [raw]
    order = 1
    for page in pages:
        if isinstance(page, dict):
            rec_texts = page.get("rec_texts")
            dt_polys = page.get("dt_polys") or page.get("rec_polys") or []
            if isinstance(rec_texts, (list, tuple)):
                rec_scores = page.get("rec_scores") or []
                for index, text_value in enumerate(rec_texts):
                    text = str(text_value).strip()
                    if not text:
                        continue
                    score = rec_scores[index] if index < len(rec_scores) else 0.0
                    points = dt_polys[index] if index < len(dt_polys) else []
                    blocks.append(
                        OcrBlock(
                            text=text,
                            bbox=_bbox_from_points(points),
                            confidence=float(score or 0.0),
                            reading_order=order,
                        )
                    )
                    order += 1
                continue
        lines = page if isinstance(page, list) else []
        for item in lines:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                bbox = item.get("bbox") or item.get("box") or [0, 0, 0, 0]
                blocks.append(
                    OcrBlock(
                        text=text,
                        bbox=[float(v) for v in bbox[:4]],
                        confidence=float(item.get("confidence") or item.get("score") or 0.0),
                        reading_order=order,
                        region_type=item.get("region_type") or item.get("type"),
                    )
                )
                order += 1
                continue
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            box, rec = item[0], item[1]
            if not isinstance(rec, (list, tuple)) or len(rec) < 2:
                continue
            text = str(rec[0]).strip()
            if not text:
                continue
            blocks.append(
                OcrBlock(
                    text=text,
                    bbox=_bbox_from_points(box),
                    confidence=float(rec[1]),
                    reading_order=order,
                )
            )
            order += 1
    return blocks


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr", response_model=OcrResponse)
async def ocr(
    image: UploadFile | None = File(default=None),
    file: UploadFile | None = File(default=None),
) -> OcrResponse:
    upload = image or file
    if upload is None:
        raise HTTPException(status_code=422, detail="image or file is required")
    suffix = Path(upload.filename or "frame.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await upload.read())
        image_path = Path(tmp.name)
    try:
        engine = get_ocr_engine()
        try:
            raw = engine.ocr(str(image_path), cls=True)
        except TypeError:
            raw = engine.ocr(str(image_path))
        return OcrResponse(blocks=_normalise_result(raw))
    finally:
        image_path.unlink(missing_ok=True)
