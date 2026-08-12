import stat
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1.youtube import get_youtube_cookie_store
from app.main import app
from app.services.youtube.cookies import (
    YouTubeCookieStore,
    YouTubeCookieValidationError,
)
from app.services.youtube.local_video import YtDlpLocalVideoDownloader
from app.services.youtube.transcript import NoTranscriptError, YtDlpTranscriptExtractor
from app.services.youtube.visual_analysis import FfmpegFrameExtractor

YOUTUBE_COOKIE_TEXT = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret-cookie-value\n"
)


def test_store_replaces_netscape_youtube_cookie_with_restricted_permissions(
    tmp_path: Path,
) -> None:
    cookie_path = tmp_path / "youtube-cookies.txt"
    store = YouTubeCookieStore(cookie_path)

    status = store.save(YOUTUBE_COOKIE_TEXT)

    assert status.configured is True
    assert status.file_size == len(YOUTUBE_COOKIE_TEXT.encode())
    assert stat.S_IMODE(cookie_path.stat().st_mode) == 0o600
    assert store.cookiefile() == str(cookie_path)
    assert not hasattr(status, "cookies_text")


def test_store_rejects_non_netscape_cookie_text(tmp_path: Path) -> None:
    store = YouTubeCookieStore(tmp_path / "youtube-cookies.txt")

    with pytest.raises(YouTubeCookieValidationError, match="Netscape"):
        store.save("SID=secret-cookie-value")


def test_store_rejects_cookie_text_without_youtube_domain(tmp_path: Path) -> None:
    store = YouTubeCookieStore(tmp_path / "youtube-cookies.txt")

    with pytest.raises(YouTubeCookieValidationError, match="youtube.com"):
        store.save(
            "# Netscape HTTP Cookie File\n"
            ".example.com\tTRUE\t/\tTRUE\t0\tSID\tsecret-cookie-value\n"
        )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr("app.main._mark_interrupted_youtube_summaries", lambda: None)
    monkeypatch.setattr("app.main._enqueue_unfinished_youtube_summaries", lambda: None)
    monkeypatch.setattr("app.main._enqueue_missing_youtube_local_video_downloads", lambda: None)
    app.dependency_overrides[get_youtube_cookie_store] = lambda: YouTubeCookieStore(
        tmp_path / "youtube-cookies.txt"
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_cookie_api_persists_without_returning_secret(client: TestClient) -> None:
    saved = client.put("/api/v1/youtube/cookies", json={"cookies_text": YOUTUBE_COOKIE_TEXT})
    status = client.get("/api/v1/youtube/cookies")

    assert saved.status_code == 200
    assert status.json()["configured"] is True
    assert "secret-cookie-value" not in saved.text
    assert "secret-cookie-value" not in status.text


def test_cookie_api_test_uses_configured_file_without_exposing_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            captured.update(options)

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def extract_info(self, _url: str, download: bool) -> dict[str, bool]:
            assert download is False
            return {"ok": True}

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    client.put("/api/v1/youtube/cookies", json={"cookies_text": YOUTUBE_COOKIE_TEXT})

    response = client.post("/api/v1/youtube/cookies/test")

    assert response.json() == {
        "success": True,
        "status": "ok",
        "message": "Cookie 可用于 YouTube。",
    }
    assert captured["cookiefile"]
    assert "youtube-cookies.txt" not in response.text


def test_local_video_download_passes_cookie_file_to_yt_dlp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> None:
        captured.extend(command)
        target_dir = Path(command[command.index("-o") + 1]).parent
        (target_dir / "video.mp4").touch()

    monkeypatch.setattr("subprocess.run", fake_run)
    YtDlpLocalVideoDownloader().download(
        video_id="abc123",
        target_root=tmp_path,
        proxy_url=None,
        cookies_file="/app/private/youtube-cookies.txt",
    )

    assert ["--cookies", "/app/private/youtube-cookies.txt"] == captured[1:3]


def test_frame_download_passes_cookie_file_to_yt_dlp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> None:
        captured.extend(command)

    monkeypatch.setattr("subprocess.run", fake_run)
    FfmpegFrameExtractor()._download(
        "abc123",
        tmp_path / "video.mp4",
        proxy_url=None,
        cookies_file="/app/private/youtube-cookies.txt",
    )

    assert ["--cookies", "/app/private/youtube-cookies.txt"] == captured[1:3]


def test_subtitle_download_passes_cookie_file_to_python_yt_dlp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            captured.update(options)

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def download(self, _urls: list[str]) -> None:
            return None

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)

    with pytest.raises(NoTranscriptError):
        YtDlpTranscriptExtractor(
            cookies_file="/app/private/youtube-cookies.txt"
        ).extract("abc123")

    assert captured["cookiefile"] == "/app/private/youtube-cookies.txt"
