"""Connection encryption with versioned Fernet (Phase 3).

Supports key rotation via versioned keys. Each encrypted payload carries
its key version, allowing seamless migration.
"""

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet

# Current active key version
CURRENT_KEY_VERSION = 1


def _derive_key(raw: str) -> bytes:
    """Derive 32-byte Fernet key via SHA256."""
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


@dataclass(frozen=True)
class EncryptedPayload:
    """Versioned encrypted payload: v1|base64(ciphertext)."""
    version: int
    ciphertext: str

    def serialize(self) -> str:
        return f"v{self.version}|{self.ciphertext}"

    @classmethod
    def deserialize(cls, token: str) -> "EncryptedPayload":
        if not token or "|" not in token:
            # Legacy: no version prefix, assume v1
            return cls(version=1, ciphertext=token)
        version_str, ciphertext = token.split("|", 1)
        try:
            version = int(version_str.lstrip("v"))
        except ValueError:
            version = 1
        return cls(version=version, ciphertext=ciphertext)


class ConnectionCrypto:
    """Versioned Fernet encryption for stored DB credentials."""

    def __init__(self):
        self._keys: dict[int, Fernet] = {}
        self._load_keys()

    def _load_keys(self):
        # Primary key from ENCRYPTION_KEY (or SECRET_KEY fallback)
        primary = os.getenv("ENCRYPTION_KEY") or os.getenv("SECRET_KEY") or ""
        if not primary:
            raise RuntimeError("ENCRYPTION_KEY or SECRET_KEY must be set for encryption")
        self._keys[1] = Fernet(_derive_key(primary))

        # Optional rotation keys: ENCRYPTION_KEY_V2, ENCRYPTION_KEY_V3, ...
        for v in range(2, 10):
            key_env = f"ENCRYPTION_KEY_V{v}"
            raw = os.getenv(key_env)
            if raw:
                self._keys[v] = Fernet(_derive_key(raw))

    def _get_fernet(self, version: int) -> Fernet:
        if version not in self._keys:
            raise ValueError(f"No encryption key for version {version}")
        return self._keys[version]

    def encrypt(self, plaintext: str) -> str:
        """Encrypt with current key version."""
        if not plaintext:
            return plaintext
        f = self._keys[CURRENT_KEY_VERSION]
        token = f.encrypt(plaintext.encode()).decode()
        return EncryptedPayload(version=CURRENT_KEY_VERSION, ciphertext=token).serialize()

    def decrypt(self, token: str) -> str:
        """Decrypt using appropriate key version."""
        if not token:
            return token
        payload = EncryptedPayload.deserialize(token)
        try:
            f = self._get_fernet(payload.version)
            return f.decrypt(payload.ciphertext.encode()).decode()
        except Exception:
            # Legacy fallback: value was stored plaintext before encryption
            return token


# Global singleton
crypto = ConnectionCrypto()

# Backward-compatible helpers
def encrypt_value(plaintext: str) -> str:
    return crypto.encrypt(plaintext)


def decrypt_value(token: str) -> str:
    return crypto.decrypt(token)