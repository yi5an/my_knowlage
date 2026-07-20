"""Visual evidence extraction for YouTube videos.

The service is intentionally split from the summary pipeline: frame sampling,
OCR, and slide/mind-map structuring are best-effort enrichment. A failure here
must never fail the transcript summary.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.models import Video, VideoFrameAnalysis
from app.schemas.youtube import FrameType, OcrBlock, VideoFrameAnalysisResult
from app.services.youtube.chapters import seconds_to_str

logger = logging.getLogger(__name__)


class VisualAnalysisError(Exception):
    """Raised when visual analysis cannot run."""


@dataclass(frozen=True)
class ExtractedFrame:
    timestamp_sec: float
    image_path: Path
    perceptual_hash: str


@dataclass(frozen=True)
class _PositionedOcrLine:
    text: str
    bbox: list[float]
    x: float
    y: float
    level: int


class OcrClient:
    """HTTP client for a local OCR service.

    Expected contract:
      POST /ocr multipart field ``image`` -> {"blocks": [{text,bbox,confidence,...}]}
    Compatible response aliases are accepted to make local PaddleOCR wrappers
    easy to evolve without touching the KnowPilot pipeline.
    """

    def __init__(self, base_url: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def analyze_image(self, image_path: Path) -> list[OcrBlock]:
        with image_path.open("rb") as image_file:
            image_bytes = image_file.read()
            response = httpx.post(
                f"{self.base_url}/ocr",
                files={
                    "image": (image_path.name, image_bytes, "image/jpeg"),
                    "file": (image_path.name, image_bytes, "image/jpeg"),
                },
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        raw_blocks = (
            payload.get("blocks") or payload.get("ocr_blocks") or payload.get("lines") or []
        )
        if not raw_blocks and isinstance(payload.get("text"), str):
            confidence = float(payload.get("confidence") or 0.0)
            raw_blocks = [
                {
                    "text": line,
                    "bbox": [0, 0, 0, 0],
                    "confidence": confidence,
                    "reading_order": idx + 1,
                }
                for idx, line in enumerate(payload["text"].splitlines())
                if line.strip()
            ]
        blocks: list[OcrBlock] = []
        for idx, raw in enumerate(raw_blocks):
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text") or "").strip()
            if not text:
                continue
            bbox = raw.get("bbox") or raw.get("box") or [0, 0, 0, 0]
            blocks.append(
                OcrBlock(
                    text=text,
                    bbox=[float(v) for v in bbox[:4]],
                    confidence=float(raw.get("confidence") or raw.get("score") or 0.0),
                    reading_order=raw.get("reading_order") or idx + 1,
                    region_type=raw.get("region_type") or raw.get("type"),
                )
            )
        return blocks


class FfmpegFrameExtractor:
    """Download a low-resolution video stream and sample frames with ffmpeg."""

    def __init__(self, interval_sec: int = 45, max_count: int = 24) -> None:
        self.interval_sec = interval_sec
        self.max_count = max_count

    def extract(
        self,
        video_id: str,
        output_dir: Path,
        *,
        proxy_url: str | None,
    ) -> list[ExtractedFrame]:
        output_dir.mkdir(parents=True, exist_ok=True)
        video_path = output_dir / f"{video_id}.mp4"
        self._download(video_id, video_path, proxy_url=proxy_url)
        return self._sample(video_path, output_dir)

    def _download(self, video_id: str, video_path: Path, *, proxy_url: str | None) -> None:
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "-f",
            "bestvideo[height<=720][ext=mp4]/best[height<=720]/best",
            "-o",
            str(video_path),
        ]
        if proxy_url:
            cmd.extend(["--proxy", proxy_url])
        cmd.append(f"https://www.youtube.com/watch?v={video_id}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise VisualAnalysisError(f"yt-dlp frame download failed: {detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise VisualAnalysisError("yt-dlp frame download timed out") from exc

    def _sample(self, video_path: Path, output_dir: Path) -> list[ExtractedFrame]:
        pattern = output_dir / "frame_%04d.jpg"
        fps = f"fps=1/{max(self.interval_sec, 1)}"
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vf",
            fps,
            "-frames:v",
            str(self.max_count),
            "-q:v",
            "3",
            str(pattern),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise VisualAnalysisError(f"ffmpeg frame extraction failed: {detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise VisualAnalysisError("ffmpeg frame extraction timed out") from exc

        frames: list[ExtractedFrame] = []
        for idx, path in enumerate(sorted(output_dir.glob("frame_*.jpg"))[: self.max_count]):
            frames.append(
                ExtractedFrame(
                    timestamp_sec=float(idx * self.interval_sec),
                    image_path=path,
                    perceptual_hash=perceptual_hash(path),
                )
            )
        return frames


def perceptual_hash(image_path: Path) -> str:
    try:
        import imagehash
        from PIL import Image

        with Image.open(image_path) as image:
            return str(imagehash.phash(image))
    except Exception as exc:  # noqa: BLE001
        raise VisualAnalysisError(f"could not hash frame {image_path}: {exc}") from exc


def _hex_hamming(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 9999


def is_near_duplicate_hash(left: str, right: str, *, threshold: int) -> bool:
    return _hex_hamming(left, right) <= threshold


def _ordered_blocks(blocks: list[OcrBlock]) -> list[OcrBlock]:
    return sorted(
        blocks,
        key=lambda b: (
            b.reading_order if b.reading_order is not None else 9999,
            b.bbox[1] if len(b.bbox) > 1 else 0,
            b.bbox[0] if b.bbox else 0,
        ),
    )


def classify_frame(blocks: list[OcrBlock]) -> FrameType:
    text = "\n".join(b.text for b in blocks).lower()
    region_types = {str(b.region_type or "").lower() for b in blocks}
    if "table" in region_types or any(marker in text for marker in ("同比", "环比", "roe", "eps")):
        return "table"
    if "chart" in region_types or any(marker in text for marker in ("趋势", "收益率", "增长率")):
        return "chart"
    if any(marker in text for marker in ("->", "→", "思维导图", "脑图", "框架", "路径")):
        return "mindmap"
    if "title" in region_types or len(blocks) >= 4:
        return "slide"
    if blocks:
        return "screen_text"
    return "other"


def structured_notes_from_ocr(blocks: list[OcrBlock]) -> dict[str, Any]:
    ordered = _ordered_blocks(blocks)
    lines = [b.text.strip() for b in ordered if b.text.strip()]
    if not lines:
        return {"title": "", "bullets": [], "text": ""}
    tree = _structured_tree_from_positioned_blocks(lines[0], ordered)
    return {
        "title": lines[0],
        "bullets": lines[1:],
        "text": "\n".join(lines),
        **({"tree": tree} if tree else {}),
    }


def _structured_tree_from_positioned_blocks(
    title: str,
    blocks: list[OcrBlock],
) -> dict[str, Any] | None:
    candidates: list[tuple[str, list[float], float, float]] = []
    for block in blocks:
        text = _clean_visual_tree_text(block.text)
        if not text or text == title.strip():
            continue
        if not _has_useful_bbox(block.bbox):
            continue
        x1, y1, x2, y2 = _normal_bbox(block.bbox)
        if _is_visual_noise(text, x1):
            continue
        candidates.append((text, [x1, y1, x2, y2], x1, (y1 + y2) / 2))

    if len(candidates) < 3:
        return None

    boundaries = _column_boundaries([candidate[2] for candidate in candidates])
    positioned = [
        _PositionedOcrLine(
            text=text,
            bbox=bbox,
            x=x,
            y=y,
            level=_level_for_x(x, boundaries),
        )
        for text, bbox, x, y in candidates
    ]
    levels = {
        1: sorted((line for line in positioned if line.level == 1), key=lambda line: line.y),
        2: sorted((line for line in positioned if line.level == 2), key=lambda line: line.y),
        3: sorted((line for line in positioned if line.level >= 3), key=lambda line: line.y),
    }
    if not levels[1] or not levels[2]:
        return None

    level_one_nodes: list[dict[str, Any]] = []
    level_one_by_text: dict[str, dict[str, Any]] = {}
    for line in levels[1]:
        node = {"title": line.text, "children": []}
        level_one_nodes.append(node)
        level_one_by_text[line.text] = node

    level_two_entries: list[tuple[_PositionedOcrLine, dict[str, Any]]] = []
    for line in levels[2]:
        parent_line = _nearest_line(line, levels[1])
        if parent_line is None:
            continue
        node = _node_from_branch_text(line.text)
        level_one_by_text[parent_line.text]["children"].append(node)
        level_two_entries.append((line, node))

    for line in levels[3]:
        parent_entry = _nearest_entry(line, level_two_entries)
        if parent_entry is None:
            continue
        parent_entry[1]["children"].append({"title": line.text, "children": []})

    children = [_prune_empty_children(node) for node in level_one_nodes if node["children"]]
    if not children:
        return None
    return {"title": title.strip(), "children": children}


def _clean_visual_tree_text(text: str) -> str:
    return text.strip()


def _has_useful_bbox(bbox: list[float]) -> bool:
    if len(bbox) < 4:
        return False
    x1, y1, x2, y2 = _normal_bbox(bbox)
    return (x2 - x1) > 1 and (y2 - y1) > 1


def _normal_bbox(bbox: list[float]) -> tuple[float, float, float, float]:
    x_values = [float(bbox[0]), float(bbox[2])]
    y_values = [float(bbox[1]), float(bbox[3])]
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _is_visual_noise(text: str, x1: float) -> bool:
    if len(text) <= 1 and not text.isalnum():
        return True
    if x1 < 50 or x1 > 1120:
        return True
    if re.fullmatch(r"[（(]?\d{1,2}[./月-]\d{1,2}[日）)]?", text):
        return True
    noise_markers = (
        "你可随时",
        "需要在",
        "息框里",
        "非官方",
        "不构成投资建议",
        "香港时间",
    )
    return any(marker in text for marker in noise_markers) or text in {"斤师", "业分析"}


def _column_boundaries(xs: list[float]) -> list[float]:
    unique_xs = sorted(set(xs))
    if len(unique_xs) < 3:
        return []
    boundaries: list[float] = []
    for index in range(len(unique_xs) - 1):
        left = unique_xs[index]
        right = unique_xs[index + 1]
        if right - left >= 40:
            boundaries.append((left + right) / 2)
        if len(boundaries) == 2:
            break
    if len(boundaries) < 2 or boundaries[1] - boundaries[0] < 80:
        return []
    return boundaries


def _level_for_x(x: float, boundaries: list[float]) -> int:
    if not boundaries:
        return 1
    return 1 + sum(1 for boundary in boundaries if x > boundary)


def _nearest_line(
    line: _PositionedOcrLine,
    candidates: list[_PositionedOcrLine],
) -> _PositionedOcrLine | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs(candidate.y - line.y))


def _nearest_entry(
    line: _PositionedOcrLine,
    entries: list[tuple[_PositionedOcrLine, dict[str, Any]]],
) -> tuple[_PositionedOcrLine, dict[str, Any]] | None:
    if not entries:
        return None
    return min(entries, key=lambda entry: abs(entry[0].y - line.y))


def _node_from_branch_text(text: str) -> dict[str, Any]:
    split = _split_visual_tree_branch(text)
    if split is None:
        return {"title": text, "children": []}
    heading, detail = split
    return {"title": heading, "children": [{"title": detail, "children": []}]}


def _split_visual_tree_branch(text: str) -> tuple[str, str] | None:
    for delimiter in ("：", ":"):
        if delimiter not in text:
            continue
        heading, detail = text.split(delimiter, 1)
        heading = heading.strip()
        detail = detail.strip()
        if 2 <= len(heading) <= 12 and detail:
            return heading, detail
    return None


def _prune_empty_children(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": node["title"],
        "children": [_prune_empty_children(child) for child in node.get("children", [])],
    }


def _avg_confidence(blocks: list[OcrBlock]) -> float:
    if not blocks:
        return 0.0
    return sum(b.confidence for b in blocks) / len(blocks)


class VideoVisualAnalysisService:
    """Analyze retained video frames and optionally persist them."""

    def __init__(
        self,
        *,
        frame_extractor: Any,
        ocr_client: Any,
        session: Session | None = None,
        storage_dir: Path | str | None = None,
        proxy_url: str | None = None,
        frame_similarity_threshold: int = 6,
        min_text_chars: int = 12,
    ) -> None:
        self.frame_extractor = frame_extractor
        self.ocr_client = ocr_client
        self.session = session
        self.storage_dir = Path(storage_dir or tempfile.gettempdir())
        self.proxy_url = proxy_url
        self.frame_similarity_threshold = frame_similarity_threshold
        self.min_text_chars = min_text_chars

    def analyze(
        self,
        video: Video,
        youtube_video_id: str,
        *,
        replace_existing: bool = False,
    ) -> list[VideoFrameAnalysisResult]:
        if self.session is not None and not replace_existing:
            existing = load_frame_results(self.session, video.id)
            if existing:
                return existing
        results = self.analyze_video_id(
            youtube_video_id,
            workspace_id=video.workspace_id,
            video_row_id=video.id,
        )
        if self.session is not None and results:
            self._persist(video, results)
        return results

    def analyze_video_id(
        self,
        youtube_video_id: str,
        *,
        workspace_id: str,
        video_row_id: str,
    ) -> list[VideoFrameAnalysisResult]:
        output_dir = self.storage_dir / "youtube_frames" / youtube_video_id
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{youtube_video_id}_", dir=output_dir.parent))
        try:
            frames = self.frame_extractor.extract(
                youtube_video_id,
                temp_dir,
                proxy_url=self.proxy_url,
            )
            kept_hashes: list[str] = []
            results: list[VideoFrameAnalysisResult] = []
            for frame in frames:
                if any(
                    is_near_duplicate_hash(
                        frame.perceptual_hash,
                        old_hash,
                        threshold=self.frame_similarity_threshold,
                    )
                    for old_hash in kept_hashes
                ):
                    continue
                blocks = self.ocr_client.analyze_image(frame.image_path)
                notes = structured_notes_from_ocr(blocks)
                ocr_text = str(notes.get("text") or "")
                if len(ocr_text) < self.min_text_chars:
                    continue
                kept_hashes.append(frame.perceptual_hash)
                results.append(
                    VideoFrameAnalysisResult(
                        timestamp_sec=frame.timestamp_sec,
                        timestamp_str=seconds_to_str(int(frame.timestamp_sec)),
                        image_path=str(output_dir / frame.image_path.name),
                        perceptual_hash=frame.perceptual_hash,
                        frame_type=classify_frame(blocks),
                        ocr_text=ocr_text,
                        ocr_blocks=blocks,
                        structured_notes=notes,
                        confidence=_avg_confidence(blocks),
                    )
                )

            if not results:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return results
            if output_dir.exists():
                shutil.rmtree(output_dir)
            temp_dir.rename(output_dir)
            return results
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _persist(self, video: Video, results: list[VideoFrameAnalysisResult]) -> None:
        assert self.session is not None
        self.session.execute(
            delete(VideoFrameAnalysis).where(VideoFrameAnalysis.video_id == video.id)
        )
        for result in results:
            self.session.add(
                VideoFrameAnalysis(
                    id=f"vfa_{uuid4().hex}",
                    workspace_id=video.workspace_id,
                    video_id=video.id,
                    timestamp_sec=result.timestamp_sec,
                    timestamp_str=result.timestamp_str,
                    image_path=result.image_path,
                    perceptual_hash=result.perceptual_hash,
                    frame_type=result.frame_type,
                    ocr_text=result.ocr_text,
                    ocr_blocks=[b.model_dump(mode="json") for b in result.ocr_blocks],
                    structured_notes=result.structured_notes,
                    confidence=result.confidence,
                )
            )
        self.session.commit()


def build_visual_analysis_service_from_settings(
    settings: Any,
    session: Session,
) -> VideoVisualAnalysisService | None:
    if not getattr(settings, "youtube_visual_analysis_enabled", False):
        return None
    from app.services.model_runtime import ModelRuntimeResolver

    managed = ModelRuntimeResolver(session).resolve("ocr")
    ocr_base_url = (
        managed.base_url if managed is not None else getattr(settings, "ocr_base_url", None)
    )
    if not ocr_base_url:
        logger.warning("visual analysis enabled but OCR_BASE_URL is not configured")
        return None
    return VideoVisualAnalysisService(
        session=session,
        frame_extractor=FfmpegFrameExtractor(
            interval_sec=getattr(settings, "youtube_frame_interval_sec", 45),
            max_count=getattr(settings, "youtube_frame_max_count", 24),
        ),
        ocr_client=OcrClient(
            base_url=ocr_base_url,
            timeout_seconds=(
                managed.timeout_seconds
                if managed is not None
                else getattr(settings, "ocr_timeout_seconds", 60.0)
            ),
        ),
        storage_dir=Path(getattr(settings, "local_storage_dir", "./storage")),
        proxy_url=getattr(settings, "youtube_proxy_url", None),
        frame_similarity_threshold=getattr(settings, "youtube_frame_similarity_threshold", 6),
        min_text_chars=getattr(settings, "youtube_frame_min_text_chars", 12),
    )


def load_frame_results(session: Session, video_id: str) -> list[VideoFrameAnalysisResult]:
    rows = session.scalars(
        select(VideoFrameAnalysis)
        .where(VideoFrameAnalysis.video_id == video_id)
        .order_by(VideoFrameAnalysis.timestamp_sec)
    ).all()
    return [
        VideoFrameAnalysisResult(
            timestamp_sec=row.timestamp_sec,
            timestamp_str=row.timestamp_str,
            image_path=row.image_path,
            perceptual_hash=row.perceptual_hash,
            frame_type=row.frame_type,  # type: ignore[arg-type]
            ocr_text=row.ocr_text,
            ocr_blocks=[OcrBlock.model_validate(raw) for raw in row.ocr_blocks or []],
            structured_notes=row.structured_notes or {},
            confidence=row.confidence,
        )
        for row in rows
    ]
