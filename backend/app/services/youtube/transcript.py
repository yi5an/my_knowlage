"""Extract timed transcripts from YouTube videos.

The :class:`TranscriptExtractor` protocol lets the pipeline depend on an
abstraction so that tests can inject a fake without touching the network.
:class:`YouTubeTranscriptExtractor` is the real implementation backed by
``youtube-transcript-api``. Failures (no transcript, rate limited, etc.)
are surfaced as explicit error types rather than silent None returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas.youtube import Transcript, TranscriptSegment


class TranscriptError(Exception):
    """Base error for transcript extraction failures."""


class NoTranscriptError(TranscriptError):
    """The video has neither manual nor auto-generated captions."""


class TranscriptUnavailableError(TranscriptError):
    """Captions may exist but could not be fetched (rate limited, private, ...)."""


class TranscriptExtractor(Protocol):
    def extract(self, video_id: str, preferred_language: str | None = None) -> Transcript:
        ...


@dataclass(frozen=True)
class _RawSegment:
    text: str
    start: float
    duration: float


def _build_transcript(
    video_id: str, raw_segments: list[_RawSegment], *, language: str | None, source: str
) -> Transcript:
    segments = [
        TranscriptSegment(text=s.text.strip(), start_sec=s.start, duration_sec=s.duration)
        for s in raw_segments
        if s.text and s.text.strip()
    ]
    return Transcript(
        video_id=video_id,
        language=language,
        source=source,  # type: ignore[arg-type]
        segments=segments,
    )


class YouTubeTranscriptExtractor:
    """Real implementation backed by ``youtube-transcript-api``.

    The dependency is imported lazily inside :meth:`extract` so the module
    imports cleanly even when the package is not installed (e.g. CI without
    the optional dep), and so tests can monkeypatch it.
    """

    def extract(self, video_id: str, preferred_language: str | None = None) -> Transcript:
        from youtube_transcript_api import (  # type: ignore[import-untyped]
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )
        from youtube_transcript_api._errors import (  # type: ignore[import-untyped]
            VideoUnavailable,
        )

        try:
            fetched_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except (VideoUnavailable, TranscriptsDisabled) as exc:
            raise NoTranscriptError(str(exc)) from exc

        # Collect all available transcripts by iterating the TranscriptList.
        # Each item has .language_code and .is_generated.
        all_transcripts = list(fetched_list)
        if not all_transcripts:
            raise NoTranscriptError(f"no transcripts available for {video_id}")

        def matches_lang(t: object) -> bool:
            if preferred_language is None:
                return True
            return getattr(t, "language_code", "").startswith(preferred_language)

        manual = [t for t in all_transcripts if not getattr(t, "is_generated", False)]
        generated = [t for t in all_transcripts if getattr(t, "is_generated", False)]

        # Priority: manual+preferred > manual any > generated+preferred > generated any.
        candidate = None
        for pool in (manual, generated):
            preferred = [t for t in pool if matches_lang(t)]
            candidate = preferred[0] if preferred else (pool[0] if pool else None)
            if candidate is not None:
                break

        if candidate is None:
            raise NoTranscriptError(f"no usable transcript for {video_id}")

        try:
            raw = candidate.fetch()
        except Exception as exc:  # noqa: BLE001 - surface as unavailable
            raise TranscriptUnavailableError(str(exc)) from exc

        source = "manual" if not getattr(candidate, "is_generated", False) else "auto"
        raw_segments = [
            _RawSegment(
                text=snippet.text,
                start=float(snippet.start),
                duration=float(snippet.duration),
            )
            for snippet in raw
        ]
        return _build_transcript(
            video_id,
            raw_segments,
            language=getattr(candidate, "language_code", None),
            source=source,
        )


class YtDlpTranscriptExtractor:
    """Transcript extractor backed by ``yt-dlp`` instead of
    ``youtube-transcript-api``.

    yt-dlp uses a different request path (android VR player API + signed
    caption URLs) that bypasses the ``pot`` (proof-of-origin) anti-bot
    check which silently returns empty bodies from the plain timedtext
    endpoint. In environments where ``youtube-transcript-api`` fails with
    "no element found: line 1, column 0", this extractor typically still
    succeeds, so it's the preferred first attempt.

    Downloads captions as JSON3 (one event per caption cue with precise
    start ms + duration), which is easier to parse robustly than VTT.
    """

    def extract(self, video_id: str, preferred_language: str | None = None) -> Transcript:
        import json
        import os
        import tempfile

        from yt_dlp import YoutubeDL  # type: ignore[import-untyped]

        # Build the subtitle language preference list. yt-dlp tries them in
        # order; we put the preferred language first, then fall back to en.
        langs = []
        if preferred_language:
            # yt-dlp matches prefixes, so "en" covers "en-US" etc.
            langs.append(preferred_language)
        if "en" not in langs:
            langs.append("en")
        # Always allow auto-generated as a last resort within the chosen lang.
        request_langs = []
        for lang in langs:
            request_langs.append(f"{lang}-orig")  # manual first
            request_langs.append(lang)

        with tempfile.TemporaryDirectory(prefix=f"ytdlp_sub_{video_id}_") as tmp:
            outtmpl = os.path.join(tmp, "sub.%(ext)s")
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": request_langs,
                "subtitlesformat": "json3",
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
                raise TranscriptUnavailableError(
                    f"yt-dlp subtitle download failed for {video_id}: {exc}"
                ) from exc

            sub_files = sorted(
                f for f in os.listdir(tmp) if f.endswith(".json3")
            )
            if not sub_files:
                raise NoTranscriptError(
                    f"yt-dlp found no subtitles for {video_id}"
                )

            # The first downloaded file corresponds to the highest-priority
            # language that actually existed. Parse its language code + kind.
            chosen = sub_files[0]
            # Filenames look like "sub.en.json3" or "sub.en-orig.json3".
            lang_code, is_auto = self._parse_sub_filename(chosen)

            with open(os.path.join(tmp, chosen), encoding="utf-8") as fh:
                payload = json.load(fh)

        raw_segments = self._parse_json3(payload)
        if not raw_segments:
            raise NoTranscriptError(
                f"yt-dlp subtitle for {video_id} had no text segments"
            )
        return _build_transcript(
            video_id,
            raw_segments,
            language=lang_code,
            source="auto" if is_auto else "manual",
        )

    @staticmethod
    def _parse_sub_filename(filename: str) -> tuple[str, bool]:
        """Extract (language_code, is_auto_generated) from a yt-dlp sub filename.

        yt-dlp names auto-subs with the lang only (e.g. ``sub.en.json3``) and
        manual subs with a ``-orig`` suffix when requested that way, but the
        reliable signal is the ``Kind`` header inside the file. As a heuristic
        from the filename we treat bare lang as auto and ``-orig`` as manual.
        """
        stem = filename.rsplit(".", 1)[0]  # drop .json3
        # stem is like "sub.en" or "sub.en-orig"
        parts = stem.split(".")
        lang_part = parts[-1] if len(parts) > 1 else ""
        is_auto = not lang_part.endswith("-orig")
        lang_code = lang_part.removesuffix("-orig")
        return lang_code, is_auto

    @staticmethod
    def _parse_json3(payload: dict) -> list[_RawSegment]:
        """Convert YouTube JSON3 caption format into raw segments.

        Each event has ``tStartMs`` (ms), optional ``dDurationMs`` (ms), and
        ``segs`` (list of {utf8: ...}). We concatenate the utf8 pieces per
        event, drop empty/non-text cues, and convert ms → seconds.
        """
        events = payload.get("events") or []
        segments: list[_RawSegment] = []
        for ev in events:
            # Skip events that only carry formatting/positioning, no text.
            segs = ev.get("segs")
            if not segs:
                continue
            text = "".join(s.get("utf8", "") for s in segs).strip()
            if not text:
                continue
            # Strip the common "\n" alignment artifacts.
            text = text.replace("\n", " ").strip()
            if not text:
                continue
            start_ms = float(ev.get("tStartMs", 0))
            dur_ms = float(ev.get("dDurationMs", 0))
            segments.append(
                _RawSegment(
                    text=text,
                    start=start_ms / 1000.0,
                    duration=dur_ms / 1000.0,
                )
            )
        return segments


class ChainedTranscriptExtractor:
    """Try multiple extractors in order, returning the first success.

    Default chain: ``YtDlpTranscriptExtractor`` (robust to YouTube's pot
    anti-bot) → ``YouTubeTranscriptApiExtractor`` (lighter, no download).
    Each extractor's failure is logged; only if all fail do we raise the
    last error so the orchestrator can fall back to ASR.
    """

    def __init__(self, extractors: list[TranscriptExtractor] | None = None) -> None:
        if extractors is None:
            extractors = [YtDlpTranscriptExtractor(), YouTubeTranscriptExtractor()]
        self.extractors = extractors

    def extract(self, video_id: str, preferred_language: str | None = None) -> Transcript:
        import logging

        log = logging.getLogger(__name__)
        last_error: Exception | None = None
        for i, ext in enumerate(self.extractors):
            name = type(ext).__name__
            try:
                transcript = ext.extract(video_id, preferred_language=preferred_language)
                if i > 0:
                    log.info(
                        "transcript extracted via %s (fallback #%d) for %s",
                        name, i, video_id,
                    )
                return transcript
            except NoTranscriptError as exc:
                log.debug("%s: no transcript (%s)", name, exc)
                last_error = exc
            except TranscriptError as exc:
                log.debug("%s: unavailable (%s)", name, exc)
                last_error = exc
        # All extractors failed — re-raise the last error (preferring
        # NoTranscriptError so the orchestrator knows ASR is appropriate).
        if isinstance(last_error, NoTranscriptError):
            raise last_error
        raise last_error or NoTranscriptError(
            f"all transcript extractors failed for {video_id}"
        )


class FakeTranscriptExtractor:
    """Test double. Returns a canned transcript for a known video_id."""

    def __init__(
        self,
        transcripts: dict[str, Transcript] | None = None,
        *,
        failure: type[TranscriptError] | None = None,
    ) -> None:
        self.transcripts = transcripts or {}
        # When set, every extract() raises this error type (instead of the
        # default NoTranscriptError). Used to exercise the TranscriptError →
        # ASR fallback path, which mirrors real caption endpoints that return
        # malformed/empty payloads.
        self.failure = failure
        self.calls: list[str] = []

    def with_transcript(self, video_id: str, transcript: Transcript) -> FakeTranscriptExtractor:
        self.transcripts[video_id] = transcript
        return self

    def extract(self, video_id: str, preferred_language: str | None = None) -> Transcript:
        self.calls.append(video_id)
        if self.failure is not None:
            raise self.failure(f"forced failure for {video_id}")
        if video_id in self.transcripts:
            return self.transcripts[video_id]
        raise NoTranscriptError(f"no canned transcript for {video_id}")
