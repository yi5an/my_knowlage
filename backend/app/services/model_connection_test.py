from __future__ import annotations

import base64

import httpx

from app.schemas.model_management import ConnectionTestResponse, ProviderTestRequest


class ModelConnectionTester:
    def test(self, request: ProviderTestRequest) -> ConnectionTestResponse:
        base_url = request.base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {request.api_key}"} if request.api_key else {}
        try:
            if request.capability == "llm":
                response = httpx.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": request.model_name,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    timeout=request.timeout_seconds,
                )
            elif request.capability == "embedding":
                response = httpx.post(
                    f"{base_url}/embeddings",
                    headers=headers,
                    json={"model": request.model_name, "input": "ping"},
                    timeout=request.timeout_seconds,
                )
            elif request.capability == "asr":
                response = httpx.post(
                    f"{base_url}/audio/transcriptions",
                    headers=headers,
                    data={"model": request.model_name},
                    files={"file": ("test.wav", b"RIFF$\\x00\\x00\\x00WAVEfmt ", "audio/wav")},
                    timeout=request.timeout_seconds,
                )
            else:
                png = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/7wAAAABJRU5ErkJggg=="
                )
                response = httpx.post(
                    f"{base_url}/ocr",
                    headers=headers,
                    files={"image": ("test.png", png, "image/png")},
                    timeout=request.timeout_seconds,
                )
        except httpx.TimeoutException:
            return ConnectionTestResponse(status="connection_failed", message="连接超时")
        except httpx.HTTPError:
            return ConnectionTestResponse(status="connection_failed", message="无法连接到模型服务")
        if response.status_code in (401, 403):
            return ConnectionTestResponse(
                status="authentication_failed", message="API Key 鉴权失败"
            )
        if response.status_code in (404, 405):
            return ConnectionTestResponse(status="protocol_error", message="模型地址或协议不匹配")
        if response.is_error:
            return ConnectionTestResponse(
                status="capability_mismatch", message="模型不支持该能力或请求失败"
            )
        return ConnectionTestResponse(status="success", message="连接测试成功")
