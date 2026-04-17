"""
Fernet-based encryption for secrets at rest.

Used to encrypt GitHub tokens and other credentials before storing
in the database.  The key is derived from ``EIDOS_SECRET_KEY``.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazily build a Fernet instance from the configured secret key."""
    global _fernet
    if _fernet is None:
        raw = settings.secret_key.encode()
        # Derive a 32-byte key via SHA-256, then base64-encode for Fernet
        key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string; return a URL-safe base64 token."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext token back to plaintext."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.warning("Failed to decrypt token - invalid or rotated key")
        raise ValueError("Unable to decrypt token")
