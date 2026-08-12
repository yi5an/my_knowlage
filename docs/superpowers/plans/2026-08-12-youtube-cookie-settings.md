# YouTube Cookie Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an administrator securely paste, replace, test, and remove YouTube Netscape-format cookies from Settings so every yt-dlp path can use them without exposing their contents.

**Architecture:** A file-backed `YouTubeCookieStore` owns validation, atomic writes, restrictive file modes, metadata-only status, and test access. A shared `YouTubeYtDlpCredentials` value converts the current file into Python `YoutubeDL` options or CLI arguments for audio, subtitle, visual, and local-video downloads. The Settings page talks to a metadata-only YouTube settings API and never re-renders submitted text after saving.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy-free file storage, Python `yt-dlp`, React, TypeScript, Ant Design, pytest, Vitest, Docker Compose.

---

## File structure

- Create `backend/app/services/youtube/cookies.py`: validates and atomically stores the Netscape Cookie file; exposes non-secret status and yt-dlp credentials.
- Modify `backend/app/core/config.py`: declares `YOUTUBE_COOKIES_FILE` and a non-empty production default only through Compose.
- Modify `backend/app/schemas/youtube.py`: request/response contracts that never contain Cookie text on a response model.
- Modify `backend/app/api/v1/youtube.py`: metadata, save, delete, and test endpoints under `/youtube/cookies`.
- Modify `backend/app/services/youtube/asr.py`: passes `cookiefile` to Python yt-dlp.
- Modify `backend/app/services/youtube/transcript.py`: passes `cookiefile` to Python yt-dlp subtitle retrieval.
- Modify `backend/app/services/youtube/visual_analysis.py`: passes CLI `--cookies` arguments to frame downloads.
- Modify `backend/app/services/youtube/local_video.py`: passes CLI `--cookies` arguments to NAS downloads.
- Modify `backend/app/services/youtube/*` factories: resolve credentials from settings at job execution time.
- Modify `backend/tests/test_youtube_cookie_settings.py`: validation, storage, API secrecy, and yt-dlp options.
- Modify `backend/tests/test_asr_fallback.py`, `backend/tests/test_deploy_compose.py`: regression coverage for ASR and production volume mapping.
- Modify `frontend/src/services/youtubeApi.ts`: Cookie status/save/test/remove requests.
- Modify `frontend/src/pages/SettingsPage.tsx`: safe paste-only YouTube Cookie card.
- Modify `frontend/src/pages/SettingsPage.test.tsx`: page behavior tests.
- Modify `.env.example`, `docker-compose.prod.yml`, `README.md`: non-secret deployment configuration and operating instructions.

### Task 1: Secure file-backed Cookie store and contracts

**Files:**
- Create: `backend/app/services/youtube/cookies.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/schemas/youtube.py`
- Test: `backend/tests/test_youtube_cookie_settings.py`

- [ ] **Step 1: Write failing validation and persistence tests**

```python
def test_store_replaces_netscape_youtube_cookie_with_restricted_permissions(tmp_path: Path) -> None:
    store = YouTubeCookieStore(tmp_path / "youtube-cookies.txt")

    status = store.save(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tvalue\n"
    )

    assert status.configured is True
    assert status.file_size > 0
    assert stat.S_IMODE((tmp_path / "youtube-cookies.txt").stat().st_mode) == 0o600
    assert not hasattr(status, "cookies_text")


def test_store_rejects_non_netscape_cookie_text(tmp_path: Path) -> None:
    with pytest.raises(YouTubeCookieValidationError, match="Netscape"):
        YouTubeCookieStore(tmp_path / "cookies.txt").save("SID=secret")
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `cd backend && pytest tests/test_youtube_cookie_settings.py -q`

Expected: FAIL because `YouTubeCookieStore` and response contracts do not exist.

- [ ] **Step 3: Implement the minimal secure store**

```python
class YouTubeCookieStore:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def status(self) -> YouTubeCookieStatus:
        if self.path is None or not self.path.is_file():
            return YouTubeCookieStatus(configured=False, updated_at=None, file_size=None, validation_status="not_configured")
        stat_result = self.path.stat()
        return YouTubeCookieStatus(
            configured=True,
            updated_at=datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
            file_size=stat_result.st_size,
            validation_status="valid",
        )

    def save(self, cookies_text: str) -> YouTubeCookieStatus:
        _validate_cookie_text(cookies_text)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.path.parent, delete=False, mode="w", encoding="utf-8") as temp:
            temp.write(cookies_text)
            temp.flush()
            os.fchmod(temp.fileno(), 0o600)
        os.replace(temp.name, self.path)
        return self.status()

    def delete(self) -> YouTubeCookieStatus:
        if self.path and self.path.exists():
            self.path.unlink()
        return self.status()

    def cookiefile(self) -> str | None:
        return str(self.path) if self.path and self.path.is_file() else None
```

Require a valid first header, a `youtube.com` / `.youtube.com` tab-separated domain row, and a maximum 1 MiB input. Define `YouTubeCookieStatus`, `YouTubeCookieUpdate`, and `YouTubeCookieTestResponse` Pydantic models with metadata only.

- [ ] **Step 4: Run the store tests and static checks**

Run: `cd backend && pytest tests/test_youtube_cookie_settings.py -q && ruff check app/services/youtube/cookies.py app/schemas/youtube.py app/core/config.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/youtube/cookies.py backend/app/core/config.py backend/app/schemas/youtube.py backend/tests/test_youtube_cookie_settings.py
git commit -m "feat: add secure YouTube cookie store"
```

### Task 2: Metadata-only settings API and safe Cookie test

**Files:**
- Modify: `backend/app/api/v1/youtube.py`
- Modify: `backend/app/services/youtube/cookies.py`
- Modify: `backend/tests/test_youtube_cookie_settings.py`

- [ ] **Step 1: Write failing API secrecy tests**

```python
def test_cookie_api_persists_without_returning_secret(client: TestClient) -> None:
    cookie_text = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret-value\n"

    saved = client.put("/api/v1/youtube/cookies", json={"cookies_text": cookie_text})
    status = client.get("/api/v1/youtube/cookies")

    assert saved.status_code == 200
    assert status.json()["configured"] is True
    assert "secret-value" not in saved.text
    assert "secret-value" not in status.text
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `cd backend && pytest tests/test_youtube_cookie_settings.py::test_cookie_api_persists_without_returning_secret -q`

Expected: FAIL with 404 because the endpoints do not exist.

- [ ] **Step 3: Implement endpoints and test adapter**

```python
@router.get("/cookies", response_model=YouTubeCookieStatus)
def get_youtube_cookies() -> YouTubeCookieStatus:
    return _youtube_cookie_store().status()

@router.put("/cookies", response_model=YouTubeCookieStatus)
def save_youtube_cookies(payload: YouTubeCookieUpdate) -> YouTubeCookieStatus:
    return _youtube_cookie_store().save(payload.cookies_text)

@router.delete("/cookies", response_model=YouTubeCookieStatus)
def delete_youtube_cookies() -> YouTubeCookieStatus:
    return _youtube_cookie_store().delete()

@router.post("/cookies/test", response_model=YouTubeCookieTestResponse)
def test_youtube_cookies() -> YouTubeCookieTestResponse:
    return _youtube_cookie_store().test_current_cookie()
```

The test endpoint calls `YoutubeDL` with `skip_download=True`, `quiet=True`, the current `cookiefile`, and a fixed `https://www.youtube.com/robots.txt`-independent public test video URL. Catch exceptions and return a short, scrubbed status message; do not include `str(exc)` if it may contain a local path or headers.

- [ ] **Step 4: Verify API contract**

Run: `cd backend && pytest tests/test_youtube_cookie_settings.py -q && ruff check app/api/v1/youtube.py app/services/youtube/cookies.py`

Expected: PASS, with no Cookie value in any response assertion.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/youtube.py backend/app/services/youtube/cookies.py backend/tests/test_youtube_cookie_settings.py
git commit -m "feat: expose secure YouTube cookie settings"
```

### Task 3: Apply one Cookie file to every yt-dlp path

**Files:**
- Modify: `backend/app/services/youtube/asr.py`
- Modify: `backend/app/services/youtube/transcript.py`
- Modify: `backend/app/services/youtube/visual_analysis.py`
- Modify: `backend/app/services/youtube/local_video.py`
- Modify: `backend/tests/test_asr_fallback.py`
- Modify: `backend/tests/test_youtube_cookie_settings.py`

- [ ] **Step 1: Write failing propagation tests**

```python
def test_asr_passes_cookiefile_to_python_yt_dlp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            captured.update(options)
        def __enter__(self): return self
        def __exit__(self, *_args: object) -> None: return None
        def download(self, _urls: list[str]) -> None: (tmp_path / "audio.m4a").touch()

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    service = GlmAsrService(api_key="key", workspace=str(tmp_path), cookies_file="/run/secrets/youtube-cookies.txt")
    service._download_audio("video", str(tmp_path))

    assert captured["cookiefile"] == "/run/secrets/youtube-cookies.txt"
```

Add analogous command-capture tests asserting `--cookies /run/secrets/youtube-cookies.txt` for `FfmpegFrameExtractor` and `YtDlpLocalVideoDownloader`, plus a subtitle `YoutubeDL` options test.

- [ ] **Step 2: Run propagation tests and confirm RED**

Run: `cd backend && pytest tests/test_asr_fallback.py -q && pytest tests/test_youtube_cookie_settings.py -q`

Expected: FAIL because constructors and commands do not accept Cookie paths.

- [ ] **Step 3: Implement shared credentials plumbing**

```python
@dataclass(frozen=True)
class YouTubeYtDlpCredentials:
    cookiefile: str | None

    def python_options(self) -> dict[str, str]:
        return {"cookiefile": self.cookiefile} if self.cookiefile else {}

    def command_args(self) -> list[str]:
        return ["--cookies", self.cookiefile] if self.cookiefile else []
```

Resolve this object at the point each job/factory reads `get_settings()`. Merge `python_options()` into ASR and subtitle `ydl_opts`; insert `command_args()` after `yt-dlp` for visual and local-video CLI commands. Preserve the existing proxy, retry, format, and timeout behavior.

- [ ] **Step 4: Verify all four paths**

Run: `cd backend && pytest tests/test_asr_fallback.py tests/test_youtube_cookie_settings.py -q && ruff check app/services/youtube/asr.py app/services/youtube/transcript.py app/services/youtube/visual_analysis.py app/services/youtube/local_video.py app/services/youtube/cookies.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/youtube backend/tests/test_asr_fallback.py backend/tests/test_youtube_cookie_settings.py
git commit -m "feat: use YouTube cookies for all yt-dlp downloads"
```

### Task 4: Settings-page paste interface

**Files:**
- Modify: `frontend/src/services/youtubeApi.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.test.tsx`

- [ ] **Step 1: Write failing UI tests**

```tsx
it("saves pasted YouTube cookies and clears the secret input", async () => {
  render(<SettingsPage />);
  fireEvent.click(await screen.findByRole("button", { name: "替换 Cookie" }));
  fireEvent.change(screen.getByLabelText("YouTube Cookie 文本"), { target: { value: netscapeCookie } });
  fireEvent.click(screen.getByRole("button", { name: "保存并校验" }));

  await waitFor(() => expect(fetch).toHaveBeenCalledWith(
    "/api/v1/youtube/cookies",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ cookies_text: netscapeCookie }) }),
  ));
  expect(screen.getByLabelText("YouTube Cookie 文本")).toHaveValue("");
  expect(screen.getByText("Cookie 已配置")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused UI test and confirm RED**

Run: `cd frontend && npm run test -- SettingsPage.test.tsx`

Expected: FAIL because the Cookie controls and API client do not exist.

- [ ] **Step 3: Add client methods and UI card**

```ts
export type YouTubeCookieStatus = {
  configured: boolean;
  updated_at: string | null;
  file_size: number | null;
  validation_status: "valid" | "not_configured";
};

export function saveYouTubeCookies(cookiesText: string) {
  return apiRequest<YouTubeCookieStatus>("/youtube/cookies", {
    method: "PUT", body: { cookies_text: cookiesText },
  });
}
```

Render only status and metadata initially. Reveal a `TextArea` when the user clicks “替换 Cookie”; bind it only to component state. On successful save, call `setCookiesText("")` and collapse the editor. Use Ant Design `Popconfirm` for deletion. Do not pass Cookie text to browser storage, URL parameters, toast messages, or error rendering.

- [ ] **Step 4: Verify page behavior and build**

Run: `cd frontend && npm run test -- SettingsPage.test.tsx && npm run lint && npm run build`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/youtubeApi.ts frontend/src/pages/SettingsPage.tsx frontend/src/pages/SettingsPage.test.tsx
git commit -m "feat: add YouTube cookie settings UI"
```

### Task 5: Production secret mount and documentation

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `backend/tests/test_deploy_compose.py`

- [ ] **Step 1: Write failing Compose assertions**

```python
def test_production_backend_mounts_youtube_cookie_file_read_only() -> None:
    backend = _production_backend()

    assert backend["environment"]["YOUTUBE_COOKIES_FILE"] == "/run/secrets/youtube-cookies.txt"
    assert "${KNOWPILOT_PROD_YOUTUBE_COOKIES_FILE:-/home/yi5an/knowpilot/secrets/youtube-cookies.txt}:/run/secrets/youtube-cookies.txt:ro" in backend["volumes"]
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `cd backend && pytest tests/test_deploy_compose.py::test_production_backend_mounts_youtube_cookie_file_read_only -q`

Expected: FAIL because the production file mount does not exist.

- [ ] **Step 3: Implement deployment safeguards and documentation**

Add the read-only single-file Compose mount and `YOUTUBE_COOKIES_FILE` container setting. `.env.example` may document the file path variable but must not include any Cookie value. Document these exact host preparation commands:

```bash
install -d -m 700 /home/yi5an/knowpilot/secrets
install -m 600 /dev/null /home/yi5an/knowpilot/secrets/youtube-cookies.txt
```

Then paste Cookie through Settings; refresh it from a dedicated account and same proxy exit; never commit or send it via chat.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
cd backend && pytest && ruff check .
cd ../frontend && npm run test && npm run lint && npm run build
```

Expected: PASS. Existing non-failing UI warnings may remain, but there must be no test failures or lint errors.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.prod.yml .env.example README.md backend/tests/test_deploy_compose.py
git commit -m "docs: configure secure YouTube cookie settings"
```
