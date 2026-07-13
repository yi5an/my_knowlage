from __future__ import annotations

from app.services.investment.brightdata import BrightDataClient


class RecordingBrightDataClient(BrightDataClient):
    def __init__(self) -> None:
        super().__init__(api_key="test-key", base_url="https://bright.test")
        self.requests: list[tuple[str, str, object | None]] = []

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: object | None = None,
    ) -> object:
        self.requests.append((method, url, payload))
        return {"snapshot_id": "sd_test"}


def test_submit_x_posts_uses_profile_url_discovery_payload() -> None:
    client = RecordingBrightDataClient()

    snapshot_id = client.submit_x_posts_by_profiles(["https://x.com/elonmusk"])

    assert snapshot_id == "sd_test"
    method, url, payload = client.requests[0]
    assert method == "POST"
    assert "discover_by=profile_url" in url
    assert payload == [{"url": "https://x.com/elonmusk"}]


def test_brightdata_client_uses_extended_default_timeout() -> None:
    client = BrightDataClient(api_key="test-key")

    assert client.timeout_seconds == 120
