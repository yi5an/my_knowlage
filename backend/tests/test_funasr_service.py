"""Regression coverage for the managed FunASR service source."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient


def _load_funasr_server() -> ModuleType:
    server_path = Path(__file__).parents[2] / "deploy" / "funasr-service" / "server.py"
    spec = spec_from_file_location("funasr_service_under_test", server_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _EmptyResultModel:
    def generate(self, **_: object) -> list[dict[str, str]]:
        return []


def test_empty_funasr_result_returns_empty_transcription(monkeypatch) -> None:
    server = _load_funasr_server()
    monkeypatch.setattr(server, "load_model", lambda _: _EmptyResultModel())

    with TestClient(server.app) as client:
        response = client.post(
            "/v1/audio/transcriptions",
            data={"model": "fun-asr-nano"},
            files={"file": ("silent.wav", b"RIFF", "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json() == {"text": ""}


def test_empty_funasr_result_preserves_verbose_response_shape(monkeypatch) -> None:
    server = _load_funasr_server()
    monkeypatch.setattr(server, "load_model", lambda _: _EmptyResultModel())

    with TestClient(server.app) as client:
        response = client.post(
            "/v1/audio/transcriptions",
            data={"model": "fun-asr-nano", "response_format": "verbose_json"},
            files={"file": ("silent.wav", b"RIFF", "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json()["text"] == ""
    assert response.json()["segments"] == []
    assert "duration" in response.json()
