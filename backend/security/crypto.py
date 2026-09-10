import base64
import hashlib
import os


def _get_fernet():
    """Return Fernet instance keyed from ENCRYPTION_KEY or SECRET_KEY."""
    from cryptography.fernet import Fernet

    raw = os.getenv("ENCRYPTION_KEY") or os.getenv("SECRET_KEY") or ""
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY or SECRET_KEY must be set for encryption")
    # Derive 32-byte key via SHA256, then base64-encode for Fernet
    digest = hashlib.sha256(raw.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(token: str) -> str:
    if not token:
        return token
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except Exception:
        # Fallback: value was stored plaintext before encryption was added
        return token
