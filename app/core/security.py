import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_NONCE_LEN = 12


def validate_security_keys() -> None:
    """Refuse application boot if mandatory security secrets are not configured."""
    jwt_secret = settings.get_jwt_secret()
    if not jwt_secret:
        raise RuntimeError(
            "Application refused to boot: Missing JWT secret key. "
            "Set JWT_SECRET or JWT_SECRET_KEY in environment or .env."
        )

    if not settings.AES_MASTER_KEY:
        raise RuntimeError(
            "Application refused to boot: Missing AES master key. "
            "Set AES_MASTER_KEY (32 bytes base64) in environment or .env."
        )

    try:
        key = base64.b64decode(settings.AES_MASTER_KEY)
        if len(key) != 32:
            raise ValueError("AES_MASTER_KEY must decode to exactly 32 bytes")
    except Exception as e:
        raise RuntimeError(
            f"Application refused to boot: Invalid AES_MASTER_KEY ({e})."
        )


def _master_key() -> bytes:
    if not settings.AES_MASTER_KEY:
        raise ValueError("AES_MASTER_KEY is not set")
    key = base64.b64decode(settings.AES_MASTER_KEY)
    if len(key) != 32:
        raise ValueError("AES_MASTER_KEY must decode to exactly 32 bytes")
    return key


def encrypt(plaintext: str, aad: str | None = None) -> str:
    """AES-256-GCM. Returns base64(nonce || ciphertext || tag)."""
    aes = AESGCM(_master_key())
    nonce = os.urandom(_NONCE_LEN)
    ct = aes.encrypt(nonce, plaintext.encode(), aad.encode() if aad else None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(blob: str, aad: str | None = None) -> str:
    raw = base64.b64decode(blob)
    nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    aes = AESGCM(_master_key())
    return aes.decrypt(nonce, ct, aad.encode() if aad else None).decode()
