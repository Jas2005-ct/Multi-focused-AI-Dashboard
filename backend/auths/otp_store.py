import os
import time
import secrets
import threading
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "300"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))


class OTPStore(ABC):
    @abstractmethod
    def save(self, email: str, otp: str) -> None: ...
    @abstractmethod
    def get(self, email: str) -> Optional[Tuple[str, float, int]]:
        """Returns (otp, expiry_timestamp, attempts) or None"""
    @abstractmethod
    def delete(self, email: str) -> None: ...
    @abstractmethod
    def increment_attempts(self, email: str) -> None: ...


class MemoryOTPStore(OTPStore):
    """Dev: in-process dict + Lock. Not shared across workers."""

    def __init__(self):
        self._store: dict = {}
        self._lock = threading.Lock()

    def save(self, email: str, otp: str) -> None:
        expiry = time.time() + OTP_TTL_SECONDS
        with self._lock:
            self._store[email] = (otp, expiry, 0)

    def get(self, email: str) -> Optional[Tuple[str, float, int]]:
        with self._lock:
            entry = self._store.get(email)
            if not entry:
                return None
            otp, expiry, attempts = entry
            if time.time() > expiry:
                self._store.pop(email, None)
                return None
            return entry

    def delete(self, email: str) -> None:
        with self._lock:
            self._store.pop(email, None)

    def increment_attempts(self, email: str) -> None:
        with self._lock:
            entry = self._store.get(email)
            if entry:
                otp, expiry, attempts = entry
                self._store[email] = (otp, expiry, attempts + 1)


class RedisOTPStore(OTPStore):
    """Prod: shared Redis with TTL. Atomic via single-threaded commands."""

    def __init__(self, redis_url: str):
        import redis

        self.r = redis.from_url(redis_url, decode_responses=True)

    def _key(self, email: str) -> str:
        return f"otp:{email.lower()}"

    def save(self, email: str, otp: str) -> None:
        # value = otp:attempts, TTL handles expiry
        self.r.setex(self._key(email), OTP_TTL_SECONDS, f"{otp}:0")

    def get(self, email: str) -> Optional[Tuple[str, float, int]]:
        val = self.r.get(self._key(email))
        if not val:
            return None
        try:
            otp, attempts = val.split(":")
            ttl = self.r.ttl(self._key(email))
            # ttl -1 = no expiry, -2 = missing; treat as expired
            if ttl < 0:
                return None
            expiry = time.time() + ttl
            return (otp, expiry, int(attempts))
        except Exception:
            return None

    def delete(self, email: str) -> None:
        self.r.delete(self._key(email))

    def increment_attempts(self, email: str) -> None:
        key = self._key(email)
        val = self.r.get(key)
        if not val:
            return
        try:
            otp, attempts = val.split(":")
            attempts = int(attempts) + 1
            ttl = self.r.ttl(key)
            if ttl < 0:
                ttl = OTP_TTL_SECONDS
            # need to check max attempts -> caller deletes, but update here
            self.r.setex(key, ttl, f"{otp}:{attempts}")
            if attempts >= OTP_MAX_ATTEMPTS:
                # let caller delete, but we keep until caller decides
                pass
        except Exception as e:
            logger.warning(f"Redis increment failed: {e}")


def get_otp_store() -> OTPStore:
    backend = os.getenv("OTP_BACKEND", "").lower()
    redis_url = os.getenv("REDIS_URL", "")

    # Explicit backend env wins
    if backend == "redis" and redis_url:
        try:
            store = RedisOTPStore(redis_url)
            # probe connection
            store.r.ping()
            logger.info(f"OTP store: Redis ({redis_url.split('@')[-1]})")
            return store
        except Exception as e:
            logger.warning(f"Redis OTP store failed ({e}), falling back to memory")
    elif backend == "redis" and not redis_url:
        logger.warning("OTP_BACKEND=redis but REDIS_URL not set, falling back to memory")

    # Auto-detect: if REDIS_URL present, try Redis
    if redis_url and not backend:
        try:
            import redis  # noqa
            store = RedisOTPStore(redis_url)
            store.r.ping()
            logger.info(f"OTP store: auto Redis ({redis_url.split('@')[-1]})")
            return store
        except Exception:
            pass

    logger.info("OTP store: Memory (dev)")
    return MemoryOTPStore()


# Singleton — factory reads env once at import; callers use this instance
otp_store = get_otp_store()


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
