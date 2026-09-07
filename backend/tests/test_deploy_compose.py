from pathlib import Path

import yaml


def test_production_backend_uses_container_reachable_proxy_default() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    compose = yaml.safe_load(compose_path.read_text())

    environment = compose["services"]["backend"]["environment"]

    assert (
        environment["YOUTUBE_PROXY_URL"]
        == "${KNOWPILOT_PROD_YOUTUBE_PROXY_URL:-http://mihomo:7890}"
    )
    assert (
        environment["HTTP_PROXY"]
        == "${KNOWPILOT_PROD_HTTP_PROXY:-http://mihomo:7890}"
    )
    assert (
        environment["HTTPS_PROXY"]
        == "${KNOWPILOT_PROD_HTTPS_PROXY:-http://mihomo:7890}"
    )
    assert "host.docker.internal:7890" not in "\n".join(environment.values())


def test_production_backend_mounts_nas_video_directory() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    compose = yaml.safe_load(compose_path.read_text())

    backend = compose["services"]["backend"]

    assert (
        backend["environment"]["YOUTUBE_LOCAL_VIDEO_DIR"]
        == "${KNOWPILOT_PROD_YOUTUBE_LOCAL_VIDEO_DIR:-/mnt/knowpilot-nas/youtube}"
    )
    assert "/mnt/knowpilot-nas/youtube:/mnt/knowpilot-nas/youtube" in backend["volumes"]


def test_production_backend_has_a_private_persistent_cookie_volume() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    compose = yaml.safe_load(compose_path.read_text())

    backend = compose["services"]["backend"]

    assert backend["environment"]["YOUTUBE_COOKIES_FILE"] == "/app/private/youtube-cookies.txt"
    assert "backend_private:/app/private" in backend["volumes"]
    assert "backend_private" in compose["volumes"]
    assert all(
        "backend_private" not in service.get("volumes", [])
        for name, service in compose["services"].items()
        if name != "backend"
    )


def test_development_backend_keeps_cookies_out_of_the_source_bind_mount() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.dev.yml"
    compose = yaml.safe_load(compose_path.read_text())

    backend = compose["services"]["backend"]

    assert backend["environment"]["YOUTUBE_COOKIES_FILE"] == "/app/private/youtube-cookies.txt"
    assert "backend_private:/app/private" in backend["volumes"]
    assert "backend_private" in compose["volumes"]
