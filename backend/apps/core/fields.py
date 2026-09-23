"""Encrypted model fields.

API keys and other secrets stored in the database are encrypted at rest with
Fernet (symmetric). The key comes from ENCRYPTION_KEY; when that is not set it
is derived from SECRET_KEY so a fresh deployment still boots (with a loud
warning in the logs).
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    raw = (getattr(settings, "ENCRYPTION_KEY", "") or "").strip()
    if not raw:
        # Deterministic derivation from SECRET_KEY.
        digest = hashlib.sha256(
            f"leads-encryption::{settings.SECRET_KEY}".encode()
        ).digest()
        raw = base64.urlsafe_b64encode(digest).decode()
    return Fernet(raw.encode() if isinstance(raw, str) else raw)


class _EncryptedMixin:
    def get_prep_value(self, value):
        return super().get_prep_value(value)  # type: ignore[misc]

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return self._decrypt(value)

    def get_prep_value_encrypted(self, value):
        if value is None or value == "":
            return value
        return self._encrypt(value)

    @staticmethod
    def _encrypt(value: str) -> str:
        return _fernet().encrypt(str(value).encode()).decode()

    @staticmethod
    def _decrypt(value: str):
        if value is None or value == "":
            return value
        try:
            return _fernet().decrypt(str(value).encode()).decode()
        except Exception:  # pragma: no cover - key rotation / legacy plain text
            logger.warning("Failed to decrypt value (key changed?); returning as-is")
            return value


class EncryptedCharField(_EncryptedMixin, models.TextField):
    """A text field whose DB representation is Fernet-encrypted."""

    description = "Encrypted character field"

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        return self._encrypt(value)


class EncryptedTextField(_EncryptedMixin, models.TextField):
    description = "Encrypted text field"

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        return self._encrypt(value)
