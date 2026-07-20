from urllib.error import URLError

from app.services.youtube.fetcher import RestYouTubeFetcher


class _Response:
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"items": []}'


class _Opener:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, _request: object, timeout: int) -> _Response:
        self.calls += 1
        if self.calls == 1:
            raise URLError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF")
        return _Response()


def test_rest_fetcher_retries_tls_eof_then_returns_payload(monkeypatch) -> None:
    opener = _Opener()
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *_handlers: opener,
    )
    sleeps: list[float] = []
    monkeypatch.setattr("app.services.youtube.fetcher.time.sleep", sleeps.append)
    fetcher = RestYouTubeFetcher(api_key="key", proxy_url="http://proxy")

    assert fetcher._get("videos", {"part": "snippet"}) == {"items": []}
    assert opener.calls == 2
    assert sleeps == [0.5]
