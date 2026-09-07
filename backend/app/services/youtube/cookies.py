"""Secure, file-backed YouTube Cookie storage and yt-dlp credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.schemas.youtube import YouTubeCookieStatus, YouTubeCookieTestResponse

MAX_COOKIE_BYTES = 1024 * 1024
_NETSCAPE_HEADERS = ("# HTTP Cookie File", "# Netscape HTTP Cookie File")


class YouTubeCookieValidationError(ValueError):
    """The pasted text is not a safe, usable Netscape Cookie file."""


@dataclass(frozen=True)
class YouTubeYtDlpCredentials:
    cookiefile: str | None

    def python_options(self) -> dict[str, str]:
        return {"cookiefile": self.cookiefile} if self.cookiefile else {}

    def command_args(self) -> list[str]:
        return ["--cookies", self.cookiefile] if self.cookiefile else []


class YouTubeCookieStore:
    def __init__(self, path: Path | str | None, *, proxy_url: str | None = None) -> None:
        self.path = Path(path) if path else None
        self.proxy_url = proxy_url

    def status(self) -> YouTubeCookieStatus:
        if self.path is None or not self.path.is_file():
            return YouTubeCookieStatus(
                configured=False,
                validation_status="not_configured",
            )
        stat_result = self.path.stat()
        return YouTubeCookieStatus(
            configured=True,
            updated_at=datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
            file_size=stat_result.st_size,
            validation_status="valid",
        )

    def save(self, cookies_text: str) -> YouTubeCookieStatus:
        _validate_cookie_text(cookies_text)
        if self.path is None:
            raise RuntimeError("YOUTUBE_COOKIES_FILE is not configured")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        temp_path: str | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".youtube-cookies-",
                delete=False,
            ) as temp:
                temp.write(cookies_text)
                temp.flush()
                os.fsync(temp.fileno())
                os.fchmod(temp.fileno(), 0o600)
                temp_path = temp.name
            os.replace(temp_path, self.path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        return self.status()

    def delete(self) -> YouTubeCookieStatus:
        if self.path and self.path.exists():
            self.path.unlink()
        return self.status()

    def cookiefile(self) -> str | None:
        return str(self.path) if self.path and self.path.is_file() else None

    def credentials(self) -> YouTubeYtDlpCredentials:
        return YouTubeYtDlpCredentials(cookiefile=self.cookiefile())

    def test_current_cookie(self) -> YouTubeCookieTestResponse:
        cookiefile = self.cookiefile()
        if cookiefile is None:
            return YouTubeCookieTestResponse(
                success=False,
                status="not_configured",
                message="未配置 YouTube Cookie。",
            )
        from yt_dlp import YoutubeDL  # type: ignore[import-untyped]

        try:
            with YoutubeDL(
                {
                    "skip_download": True,
                    "extract_flat": True,
                    "playlistend": 1,
                    "quiet": True,
                    "no_warnings": True,
                    "cookiefile": cookiefile,
                    "proxy": self.proxy_url,
                }
            ) as ydl:
                ydl.extract_info(
                    "https://www.youtube.com/playlist?list=WL",
                    download=False,
                )
        except Exception:  # noqa: BLE001 - never expose upstream paths or headers
            return YouTubeCookieTestResponse(
                success=False,
                status="test_failed",
                message="YouTube 拒绝了当前 Cookie，请重新导出后再试。",
            )
        return YouTubeCookieTestResponse(
            success=True,
            status="ok",
            message="Cookie 可用于 YouTube。",
        )


def _validate_cookie_text(cookies_text: str) -> None:
    encoded = cookies_text.encode("utf-8")
    if len(encoded) > MAX_COOKIE_BYTES:
        raise YouTubeCookieValidationError("Cookie text exceeds 1 MiB")
    lines = cookies_text.splitlines()
    if not lines or lines[0].strip() not in _NETSCAPE_HEADERS:
        raise YouTubeCookieValidationError("Cookie text must use Netscape HTTP Cookie File format")
    domains = [
        line.removeprefix("#HttpOnly_")
        .split("\t", maxsplit=1)[0]
        .lstrip(".")
        .casefold()
        for line in lines[1:]
        if line
        and "\t" in line
        and (not line.startswith("#") or line.startswith("#HttpOnly_"))
    ]
    if not any(domain == "youtube.com" or domain.endswith(".youtube.com") for domain in domains):
        raise YouTubeCookieValidationError("Cookie text must include a youtube.com domain")
