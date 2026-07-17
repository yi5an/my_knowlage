from pathlib import Path

import yaml


def test_production_backend_uses_container_reachable_proxy_default() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    compose = yaml.safe_load(compose_path.read_text())

    environment = compose["services"]["backend"]["environment"]

    assert (
        environment["YOUTUBE_PROXY_URL"]
        == "${KNOWPILOT_PROD_YOUTUBE_PROXY_URL:-http://192.168.1.12:7892}"
    )
    assert (
        environment["HTTP_PROXY"]
        == "${KNOWPILOT_PROD_HTTP_PROXY:-http://192.168.1.12:7892}"
    )
    assert (
        environment["HTTPS_PROXY"]
        == "${KNOWPILOT_PROD_HTTPS_PROXY:-http://192.168.1.12:7892}"
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
