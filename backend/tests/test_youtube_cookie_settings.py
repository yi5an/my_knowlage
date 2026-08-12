import stat
from pathlib import Path

import pytest

from app.services.youtube.cookies import (
    YouTubeCookieStore,
    YouTubeCookieValidationError,
)

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
