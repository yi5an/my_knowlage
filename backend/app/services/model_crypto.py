from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.core.errors import AppError


def encrypt_api_key(value: str, settings: Settings) -> str:
    if not settings.model_encryption_key:
        raise AppError("model_encryption_not_configured", "MODEL_ENCRYPTION_KEY is required.", 503)
    return Fernet(settings.model_encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt_api_key(value: str, settings: Settings) -> str:
    if not settings.model_encryption_key:
        raise AppError("model_encryption_not_configured", "MODEL_ENCRYPTION_KEY is required.", 503)
    try:
        return Fernet(settings.model_encryption_key.encode()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise AppError(
            "model_credential_invalid", "Stored model credential cannot be decrypted.", 503
        ) from exc


def mask_api_key(value: str) -> str:
    return f"{value[:3]}…{value[-4:]}" if len(value) > 7 else "已配置"
