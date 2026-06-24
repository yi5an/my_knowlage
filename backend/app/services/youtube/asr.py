"""Speech recognition fallback for videos that have no subtitles.

When ``YouTubeTranscriptExtractor`` raises ``NoTranscriptError`` (the video
has neither manual nor auto captions), the orchestrator falls back to this
module. It downloads the audio with ``yt-dlp``, splits it into short
windows with ``ffmpeg``, and transcribes each window through BigModel's
``GLM-ASR-2512`` endpoint.

Why split: GLM-ASR-2512 caps each request at ~30s / 25MB of audio. A 1h
video therefore becomes ~120 windows. Each window is transcribed on its
own, and the previous window's text is passed as ``context`` so the model
keeps consistent capitalization/punctuation across boundaries.

The module exposes a :class:`AsrService` protocol so tests can inject a
fake without touching the network or shelling out to ffmpeg/yt-dlp.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.schemas.youtube import Transcript, TranscriptSegment

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


class AsrError(Exception):
    """Base error for the ASR fallback pipeline."""


class AudioDownloadError(AsrError):
    """yt-dlp could not download the audio."""


class AudioSplitError(AsrError):
    """ffmpeg could not split the downloaded audio."""


class AsrTranscriptionError(AsrError):
    """The GLM-ASR endpoint rejected the request or returned no text."""


@dataclass(frozen=True)
class _AudioWindow:
    """A 28s slice of the original audio, with its absolute start time."""

    path: str
    start_sec: float


class AsrService(Protocol):
    """Pluggable ASR fallback. Real impl is :class:`GlrmAsrService`."""

    def transcribe(self, video_id: str) -> Transcript:
        ...


def _format_ts(sec: float) -> str:
    """Seconds → ``mm:ss`` (or ``h:mm:ss`` for long videos). Display only."""
    s = int(round(sec))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class GlmAsrService:
    """Real ASR pipeline: yt-dlp download → ffmpeg split → GLM-ASR-2512.

    Heavy operations are intentionally synchronous and explicit. The
    orchestrator runs summary jobs in background threads already, so
    blocking on a network transcription here is fine. All temp files live
    under one workspace dir and are cleaned up at the end.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        model: str = "glm-asr-2512",
        segment_sec: int = 28,
        workspace: str = "./storage/asr",
        language: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.segment_sec = segment_sec
        self.workspace = workspace
        # Hint for the model (e.g. "zh", "en"). None lets the model autodetect.
        self.language = language

    # ------------------------------------------------------------------ public

    def transcribe(self, video_id: str) -> Transcript:
        """Download, split and transcribe a video. Returns a timed Transcript."""
        os.makedirs(self.workspace, exist_ok=True)
        workdir = tempfile.mkdtemp(prefix=f"asr_{video_id}_", dir=self.workspace)
        try:
            audio_path = self._download_audio(video_id, workdir)
            duration = self._probe_duration(audio_path)
            windows = self._split_audio(audio_path, workdir, duration)
            logger.info(
                "asr: video %s → %d windows (%.1fs total)",
                video_id,
                len(windows),
                duration,
            )
            segments = self._transcribe_windows(windows)
            return Transcript(
                video_id=video_id,
                language=self.language,
                source="auto",
                segments=segments,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # --------------------------------------------------------------- yt-dlp

    def _download_audio(self, video_id: str, workdir: str) -> str:
        """Fetch the smallest usable audio track via yt-dlp.

        We deliberately keep the file in its native compressed format
        (m4a/aac or webm/opus — whatever YouTube serves). A 58-min video
        is ~30MB this way vs ~640MB as uncompressed WAV. The downstream
        ffmpeg split step decodes the needed 28s window per call, so we
        never need the whole track decompressed at once.
        """
        from yt_dlp import YoutubeDL  # type: ignore[import-untyped]

        outtmpl = os.path.join(workdir, "audio.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
        }
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as exc:  # noqa: BLE001
            raise AudioDownloadError(f"yt-dlp failed for {video_id}: {exc}") from exc

        candidates = [
            os.path.join(workdir, f)
            for f in os.listdir(workdir)
            if f.startswith("audio.")
        ]
        if not candidates:
            raise AudioDownloadError(f"no audio file produced for {video_id}")
        audio_path = candidates[0]
        logger.info("asr: downloaded %s (%.1f MB)", audio_path, _mb(audio_path))
        return audio_path

    # --------------------------------------------------------------- ffmpeg

    def _probe_duration(self, audio_path: str) -> float:
        """Get total audio duration in seconds via ffprobe."""
        try:
            out = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return float(out.stdout.strip() or 0.0)
        except Exception as exc:  # noqa: BLE001
            # Fallback: assume 0 → no windows. Caller handles empty.
            logger.warning("ffprobe failed (%s); assuming unknown duration", exc)
            return 0.0

    def _split_audio(
        self, audio_path: str, workdir: str, duration: float
    ) -> list[_AudioWindow]:
        """Slice the audio into ``segment_sec`` windows via ffmpeg."""
        if duration <= 0:
            return []
        step = float(self.segment_sec)
        windows: list[_AudioWindow] = []
        idx = 0
        start = 0.0
        while start < duration:
            chunk_path = os.path.join(workdir, f"chunk_{idx:04d}.wav")
            cmd = [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{step:.3f}",
                "-i",
                audio_path,
                *_FFMPEG_TO_WAV_ARGS,
                chunk_path,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            except subprocess.CalledProcessError as exc:
                raise AudioSplitError(
                    f"ffmpeg split failed at {start:.1f}s: "
                    f"{exc.stderr.decode('utf-8', 'replace')[:300]}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise AudioSplitError(f"ffmpeg split timed out at {start:.1f}s") from exc
            windows.append(_AudioWindow(path=chunk_path, start_sec=start))
            start += step
            idx += 1
        return windows

    # ------------------------------------------------------------- GLM-ASR API

    def _transcribe_windows(self, windows: list[_AudioWindow]) -> list[TranscriptSegment]:
        """POST each window to GLM-ASR-2512, carrying context between calls."""
        # Import lazily so the module imports cleanly in environments
        # without network access (tests, CI).
        import httpx

        segments: list[TranscriptSegment] = []
        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        previous_text = ""

        with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
            for i, window in enumerate(windows):
                text, duration_sec = self._post_one(
                    client, url, headers, window, previous_text
                )
                if not text:
                    logger.warning(
                        "asr: empty result for window %d @ %s",
                        i,
                        _format_ts(window.start_sec),
                    )
                    continue
                segments.append(
                    TranscriptSegment(
                        text=text.strip(),
                        start_sec=window.start_sec,
                        duration_sec=duration_sec,
                    )
                )
                # Keep a sliding context window so the next call stays coherent.
                previous_text = text[-200:]
                # Light rate limiting to be a friendly API client.
                time.sleep(0.2)
        return segments

    def _post_one(
        self,
        client: httpx.Client,
        url: str,
        headers: dict[str, str],
        window: _AudioWindow,
        context: str,
    ) -> tuple[str, float]:
        """One transcription request. Returns (text, segment_duration_sec)."""
        import httpx

        with open(window.path, "rb") as fh:
            files = {"file": ("chunk.wav", fh, "audio/wav")}
            data: dict[str, str] = {"model": self.model}
            if self.language:
                data["language"] = self.language
            if context:
                data["context"] = context
            try:
                resp = client.post(url, headers=headers, files=files, data=data)
            except httpx.HTTPError as exc:
                raise AsrTranscriptionError(
                    f"network error @ {_format_ts(window.start_sec)}: {exc}"
                ) from exc

        if resp.status_code >= 400:
            raise AsrTranscriptionError(
                f"ASR HTTP {resp.status_code} @ {_format_ts(window.start_sec)}: "
                f"{resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise AsrTranscriptionError(
                f"ASR returned non-JSON @ {_format_ts(window.start_sec)}: {resp.text[:200]}"
            ) from exc

        text = (
            payload.get("text")
            or (payload.get("result") or {}).get("text")
            or ""
        )
        return text, float(self.segment_sec)


# ffmpeg filter chain used to convert any input slice into a 16kHz mono WAV.
# Defined at module scope so it reads like a constant.
_FFMPEG_TO_WAV_ARGS = (
    "-vn",  # no video
    "-ac",
    "1",
    "-ar",
    "16000",
    "-c:a",
    "pcm_s16le",
)


def _mb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return 0.0


class FakeAsrService:
    """Test double. Returns a canned transcript for known video_ids."""

    def __init__(self, transcripts: dict[str, Transcript] | None = None) -> None:
        self.transcripts = transcripts or {}
        self.calls: list[str] = []

    def with_transcript(self, video_id: str, transcript: Transcript) -> FakeAsrService:
        self.transcripts[video_id] = transcript
        return self

    def transcribe(self, video_id: str) -> Transcript:
        self.calls.append(video_id)
        if video_id in self.transcripts:
            return self.transcripts[video_id]
        raise AsrError(f"no canned ASR transcript for {video_id}")


def build_asr_service_from_settings() -> AsrService | None:
    """Factory used by main.py / the API layer to wire the real service.

    Returns None when ASR is disabled or the key is missing, so callers
    can simply skip the fallback path without conditionals everywhere.
    """
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.asr_enabled or not settings.asr_api_key:
        return None
    return GlmAsrService(
        api_key=settings.asr_api_key,
        base_url=settings.asr_base_url,
        model=settings.asr_model,
        segment_sec=settings.asr_segment_sec,
        workspace=settings.asr_audio_workspace,
        language=settings.youtube_preferred_language,
    )
