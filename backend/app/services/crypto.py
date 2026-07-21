"""Encrypt/decrypt secrets using Fernet symmetric encryption.

The dedicated credentials key is preferred. ``CONDUCTOR_SECRET_KEY`` remains a
fallback so credentials encrypted by earlier Conductor versions stay readable.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class CredentialsEncryptionNotConfigured(RuntimeError):
    """Raised when new credentials cannot be encrypted safely."""


def _fernet_from_secret(source_key: str) -> Fernet:
    digest = hashlib.sha256(source_key.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a credential for storage."""
    source_key = settings.credentials_encryption_key
    if not source_key or len(source_key) < 32:
        raise CredentialsEncryptionNotConfigured(
            "CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY must contain at least 32 characters"
        )
    return _fernet_from_secret(source_key).encrypt(plaintext.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a credential, including values created before the dedicated key existed."""
    source_keys = [settings.credentials_encryption_key, settings.secret_key]
    for source_key in dict.fromkeys(key for key in source_keys if key):
        try:
            return _fernet_from_secret(source_key).decrypt(encrypted.encode()).decode()
        except InvalidToken:
            continue
    raise InvalidToken("Credential cannot be decrypted with the configured keys")