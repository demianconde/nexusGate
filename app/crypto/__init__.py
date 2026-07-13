"""Criptografia de segredos (BYOK) — envelope encryption AES-256-GCM."""

from .envelope import EncryptedSecret, decrypt_secret, encrypt_secret, is_configured

__all__ = ["EncryptedSecret", "decrypt_secret", "encrypt_secret", "is_configured"]
