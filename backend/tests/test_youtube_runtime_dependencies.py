from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_production_image_installs_supported_deno_runtime() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile.prod").read_text()

    assert "FROM denoland/deno:bin-" in dockerfile
    assert "COPY --from=deno /deno /usr/local/bin/deno" in dockerfile


def test_python_install_includes_the_yt_dlp_ejs_component() -> None:
    pyproject = (BACKEND_ROOT / "pyproject.toml").read_text()

    assert '"yt-dlp[default]>=' in pyproject
