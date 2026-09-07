from pathlib import Path


def test_production_youtube_proxy_defaults_to_reachable_mihomo_service() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.prod.yml").read_text()

    assert "${KNOWPILOT_PROD_YOUTUBE_PROXY_URL:-http://mihomo:7890}" in compose
    assert "${KNOWPILOT_PROD_HTTP_PROXY:-http://mihomo:7890}" in compose
    assert "${KNOWPILOT_PROD_HTTPS_PROXY:-http://mihomo:7890}" in compose
    assert "${KNOWPILOT_PROD_ALL_PROXY:-http://mihomo:7890}" in compose
