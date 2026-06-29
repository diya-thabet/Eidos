"""
Password hashing and verification for local authentication.

Uses bcrypt via passlib for secure password storage.
Falls back to hashlib-based PBKDF2 if passlib/bcrypt is not available.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from base64 import b64decode, b64encode

try:
    import bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False


def hash_password(password: str) -> str:
    """Hash a password for storage.

    Uses bcrypt if available, otherwise falls back to PBKDF2-SHA256.
    """
    if _HAS_BCRYPT:
        salt = bcrypt.gensalt(rounds=12)
        hashed: bytes = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    else:
        # Fallback: PBKDF2-SHA256
        salt = os.urandom(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return f"pbkdf2:{b64encode(salt).decode()}:{b64encode(dk).decode()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash.

    Supports both bcrypt and PBKDF2 hashes.
    """
    if not hashed:
        return False

    if hashed.startswith("pbkdf2:"):
        # PBKDF2 fallback format
        parts = hashed.split(":")
        if len(parts) != 3:
            return False
        salt = b64decode(parts[1])
        stored_dk = b64decode(parts[2])
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(dk, stored_dk)

    if _HAS_BCRYPT:
        try:
            is_valid: bool = bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
            return is_valid
        except (ValueError, TypeError):
            return False

    return False
