"""OpenAI-compatible FunASR transcription service.

The production ASR container mounts this module at ``/app/server.py``.
"""

import argparse
import logging
import os
import re
import tempfile
import time
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="FunASR OpenAI-Compatible API", version="1.0.0")

MODEL_REGISTRY: dict[str, Any] = {}
DEVICE = "cpu"

MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "sensevoice": {
        "model": "iic/SenseVoiceSmall",
        "vad_model": "fsmn-vad",
        "vad_kwargs": {"max_single_segment_time": 30000},
    },
    "paraformer": {
        "model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
    },
    "paraformer-en": {
        "model": "paraformer-en",
        "vad_model": "fsmn-vad",
    },
    "fun-asr-nano": {
        "model": "FunAudioLLM/Fun-ASR-Nano-2512",
        "hub": "ms",
        "trust_remote_code": True,
        "vad_model": "fsmn-vad",
        "vad_kwargs": {"max_single_segment_time": 30000},
    },
}


def load_model(model_name: str) -> Any:
    """Load a model and store it in the process-local registry."""
    if model_name in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_name]
    if model_name not in MODEL_CONFIGS:
        raise ValueError(f"Unknown model '{model_name}'. Available: {list(MODEL_CONFIGS.keys())}")

    from funasr import AutoModel

    config = MODEL_CONFIGS[model_name].copy()
    config["device"] = DEVICE
    config["disable_update"] = True
    logger.info("Loading model '%s' on %s...", model_name, DEVICE)
    started_at = time.monotonic()
    model = AutoModel(**config)
    logger.info("Model '%s' loaded in %.1fs", model_name, time.monotonic() - started_at)
    MODEL_REGISTRY[model_name] = model
    return model


def clean_text(text: str) -> str:
    """Remove SenseVoice control tags from a transcription."""
    return re.sub(r"<\|[^|]*\|>", "", text).strip()


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),  # noqa: B008 - FastAPI request-field declaration
    model: str = Form(default="sensevoice"),
    language: str | None = Form(default=None),
    response_format: str | None = Form(default="json"),
) -> JSONResponse:
    """Transcribe an uploaded audio file using a configured FunASR model."""
    if model not in MODEL_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' not found. Available: {list(MODEL_CONFIGS.keys())}",
        )

    suffix = os.path.splitext(file.filename)[1] if file.filename else ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
        temporary_file.write(await file.read())
        temporary_path = temporary_file.name

    try:
        asr_model = load_model(model)
        generate_kwargs: dict[str, Any] = {"input": temporary_path, "batch_size": 1}
        if language:
            generate_kwargs["language"] = language
        started_at = time.monotonic()
        result = asr_model.generate(**generate_kwargs)
        elapsed = time.monotonic() - started_at
        if not result:
            logger.info("ASR model returned no speech for %s", file.filename or temporary_path)
            if response_format == "verbose_json":
                return JSONResponse(
                    {
                        "text": "",
                        "segments": [],
                        "language": language or "auto",
                        "duration": round(elapsed, 3),
                        "model": model,
                    }
                )
            return JSONResponse({"text": ""})
        first_result = result[0]
        text = clean_text(first_result["text"])

        if response_format == "verbose_json":
            segments = [
                {
                    "start": segment.get("start", 0) / 1000.0,
                    "end": segment.get("end", 0) / 1000.0,
                    "text": clean_text(segment.get("text", "")),
                    "speaker": segment.get("spk"),
                }
                for segment in first_result.get("sentence_info", [])
            ]
            return JSONResponse(
                {
                    "text": text,
                    "segments": segments,
                    "language": language or "auto",
                    "duration": round(elapsed, 3),
                    "model": model,
                }
            )
        return JSONResponse({"text": text})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Transcription error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        os.unlink(temporary_path)


@app.get("/v1/models")
async def list_models() -> JSONResponse:
    """List available models."""
    models = [
        {
            "id": name,
            "object": "model",
            "created": 1700000000,
            "owned_by": "funasr",
            "ready": name in MODEL_REGISTRY,
        }
        for name in MODEL_CONFIGS
    ]
    return JSONResponse({"object": "list", "data": models})


@app.get("/health")
async def health() -> dict[str, Any]:
    """Report the server runtime state."""
    return {
        "status": "ok",
        "device": DEVICE,
        "models_loaded": list(MODEL_REGISTRY.keys()),
        "models_available": list(MODEL_CONFIGS.keys()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--model", default="sensevoice")
    arguments = parser.parse_args()

    global DEVICE
    DEVICE = arguments.device
    load_model(arguments.model)
    uvicorn.run(app, host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
