"""Encrypt/decrypt secrets using Fernet symmetric encryption.

Key is derived from CONDUCTOR_SECRET_KEY via SHA-256 → base64 → Fernet key.
Never exposes plaintext secrets outside this module's decrypt function.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the app's secret key."""
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a credential for storage."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored credential. Returns plaintext for use in git/API operations."""
    return _get_fernet().decrypt(encrypted.encode()).decode()