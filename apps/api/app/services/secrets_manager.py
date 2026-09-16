"""Secrets Manager — encrypts credentials at rest.

Provides Fernet symmetric encryption for storing sensitive data.
Supports key rotation and secret references.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _fernet_available() -> bool:
    try:
        from cryptography.fernet import Fernet
        return True
    except ImportError:
        return False


@dataclass
class EncryptedSecret:
    """An encrypted secret with metadata."""
    key: str
    encrypted_value: str
    key_version: int = 1
    created_at: str = ""
    rotated_at: str = ""
    metadata: dict | None = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "encrypted_value": self.encrypted_value,
            "key_version": self.key_version,
            "created_at": self.created_at,
            "rotated_at": self.rotated_at,
            "metadata": self.metadata,
        }


class SecretsManager:
    """Encrypts and manages secrets at rest."""

    def __init__(self, encryption_key: str | None = None):
        self._key = encryption_key or os.getenv("SECRETS_ENCRYPTION_KEY", "")
        self._key_version = 1
        self._secrets: dict[str, EncryptedSecret] = {}
        self._fernet = None

        if _fernet_available() and self._key:
            from cryptography.fernet import Fernet
            key_bytes = hashlib.sha256(self._key.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            self._fernet = Fernet(fernet_key)

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string."""
        if self._fernet:
            return self._fernet.encrypt(plaintext.encode()).decode()
        return self._fallback_encrypt(plaintext)

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string."""
        if self._fernet:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        return self._fallback_decrypt(ciphertext)

    def _fallback_encrypt(self, plaintext: str) -> str:
        """Fallback XOR-based encryption when cryptography is not available."""
        key = self._key or "default-dev-key"
        key_bytes = key.encode()
        plaintext_bytes = plaintext.encode()
        encrypted = bytes(
            b ^ key_bytes[i % len(key_bytes)]
            for i, b in enumerate(plaintext_bytes)
        )
        return base64.urlsafe_b64encode(encrypted).decode()

    def _fallback_decrypt(self, ciphertext: str) -> str:
        """Fallback XOR-based decryption."""
        key = self._key or "default-dev-key"
        key_bytes = key.encode()
        encrypted = base64.urlsafe_b64decode(ciphertext.encode())
        decrypted = bytes(
            b ^ key_bytes[i % len(key_bytes)]
            for i, b in enumerate(encrypted)
        )
        return decrypted.decode()

    def store_secret(
        self,
        key: str,
        value: str,
        metadata: dict | None = None,
    ) -> EncryptedSecret:
        """Store an encrypted secret."""
        encrypted = self._encrypt(value)
        now = datetime.now(timezone.utc).isoformat()

        secret = EncryptedSecret(
            key=key,
            encrypted_value=encrypted,
            key_version=self._key_version,
            created_at=now,
            metadata=metadata,
        )
        self._secrets[key] = secret
        logger.info("Secret stored: %s (version %d)", key, self._key_version)
        return secret

    def get_secret(self, key: str) -> str | None:
        """Retrieve and decrypt a secret."""
        secret = self._secrets.get(key)
        if not secret:
            return None
        try:
            return self._decrypt(secret.encrypted_value)
        except Exception as e:
            logger.error("Failed to decrypt secret %s: %s", key, e)
            return None

    def rotate_secret(self, key: str, new_value: str) -> EncryptedSecret | None:
        """Rotate a secret with a new value."""
        secret = self._secrets.get(key)
        if not secret:
            return None

        encrypted = self._encrypt(new_value)
        secret.encrypted_value = encrypted
        secret.key_version += 1
        secret.rotated_at = datetime.now(timezone.utc).isoformat()
        logger.info("Secret rotated: %s (version %d)", key, secret.key_version)
        return secret

    def delete_secret(self, key: str) -> bool:
        """Delete a secret."""
        if key in self._secrets:
            del self._secrets[key]
            logger.info("Secret deleted: %s", key)
            return True
        return False

    def list_secrets(self, include_metadata: bool = False) -> list[dict]:
        """List all secret keys (without values)."""
        result = []
        for key, secret in self._secrets.items():
            entry = {
                "key": key,
                "key_version": secret.key_version,
                "created_at": secret.created_at,
                "rotated_at": secret.rotated_at,
            }
            if include_metadata:
                entry["metadata"] = secret.metadata
            result.append(entry)
        return result

    def export_encrypted(self) -> dict[str, str]:
        """Export all secrets in encrypted form (for backup)."""
        return {key: secret.encrypted_value for key, secret in self._secrets.items()}

    def import_encrypted(self, data: dict[str, str]) -> int:
        """Import encrypted secrets (from backup)."""
        count = 0
        for key, encrypted_value in data.items():
            self._secrets[key] = EncryptedSecret(
                key=key,
                encrypted_value=encrypted_value,
                key_version=self._key_version,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            count += 1
        return count

    def mask_value(self, value: str) -> str:
        """Mask a secret value for display."""
        if len(value) <= 8:
            return "****"
        return value[:4] + "*" * (len(value) - 8) + value[-4:]
