"""Configurable rate limiting for public and provider-cost endpoints.

The default backend is an in-process sliding-window limiter intended for local
development and single-worker deployments. Multi-worker production deployments
should set ``RATE_LIMIT_BACKEND=redis`` and install
``backend/requirements-redis.txt``. If a configured shared backend is
unavailable, protected endpoints fail closed with ``503`` rather than silently
disabling limits.

Client identifiers are hashed before they are used as limiter keys, and raw IP
addresses are not logged. See ``app.core.network`` for trusted-proxy handling.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.network import resolve_client_ip

logger = logging.getLogger(__name__)

INCIDENTS_CREATE_POLICY = "incidents_create"
TRACKING_LOOKUP_POLICY = "tracking_lookup"
LOGIN_POLICY = "login"
VOICE_TRANSCRIBE_POLICY = "voice_transcribe"
VOICE_SPEAK_POLICY = "voice_speak"
AI_UNDERSTAND_POLICY = "ai_understand"
AI_ANALYZE_IMAGE_POLICY = "ai_analyze_image"

RATE_LIMIT_429_RESPONSE = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "description": (
            "Rate limit exceeded. The response includes a Retry-After header "
            "with the number of seconds to wait."
        )
    }
}


class RateLimitBackendError(RuntimeError):
    """Raised when a configured limiter backend cannot answer a check."""


class RateLimitConfigurationError(RuntimeError):
    """Raised when rate-limit configuration cannot be initialized."""


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class RateLimitBackend(Protocol):
    def check(
        self, key: str, limit: int, window_seconds: int, now: float
    ) -> RateLimitDecision: ...

    def close(self) -> None: ...


class InMemoryRateLimitBackend:
    """Thread-safe, process-local sliding-window limiter.

    This backend is not shared between worker processes. It is the documented
    development fallback and is also suitable for a single-worker deployment.
    """

    def __init__(self, *, max_keys: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, deque[float]] = {}
        self._max_keys = max(1, max_keys)

    def check(
        self, key: str, limit: int, window_seconds: int, now: float
    ) -> RateLimitDecision:
        with self._lock:
            timestamps = self._entries.get(key)
            if timestamps is None:
                if len(self._entries) >= self._max_keys:
                    self._evict_oldest()
                timestamps = deque()
                self._entries[key] = timestamps

            cutoff = now - window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= limit:
                retry_after = max(
                    1, math.ceil(timestamps[0] + window_seconds - now)
                )
                return RateLimitDecision(False, retry_after)

            timestamps.append(now)
            return RateLimitDecision(True, 0)

    def _evict_oldest(self) -> None:
        if not self._entries:
            return

        def last_seen(key: str) -> float:
            timestamps = self._entries[key]
            return timestamps[-1] if timestamps else 0.0

        oldest_key = min(self._entries, key=last_seen)
        self._entries.pop(oldest_key, None)

    def close(self) -> None:
        with self._lock:
            self._entries.clear()


class RedisRateLimitBackend:
    """Shared sliding-window limiter backed by a Redis sorted set.

    The check is atomic (Lua script), so multiple workers can share the same
    limits. The ``redis`` package is optional and imported lazily.
    """

    _SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local member = ARGV[4]
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    local count = redis.call('ZCARD', key)
    if count >= limit then
      local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
      local retry = 1
      if oldest[2] then
        retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
      end
      return {0, retry}
    end
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, window)
    return {1, 0}
    """

    def __init__(self, url: str, *, timeout_seconds: float = 1.0) -> None:
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RateLimitConfigurationError(
                "RATE_LIMIT_BACKEND=redis requires the optional 'redis' package. "
                "Install backend/requirements-redis.txt."
            ) from exc

        try:
            self._client = redis.Redis.from_url(
                url,
                socket_timeout=timeout_seconds,
                socket_connect_timeout=timeout_seconds,
                decode_responses=True,
            )
        except Exception as exc:
            raise RateLimitConfigurationError(
                "RATE_LIMIT_REDIS_URL is invalid."
            ) from exc

    def ping(self) -> None:
        try:
            self._client.ping()
        except Exception as exc:
            raise RateLimitBackendError(
                "Shared rate-limit backend is unavailable."
            ) from exc

    def check(
        self, key: str, limit: int, window_seconds: int, now: float
    ) -> RateLimitDecision:
        now_ms = int(now * 1000)
        window_ms = int(window_seconds * 1000)
        member = f"{now_ms}:{uuid.uuid4().hex}"
        try:
            result = self._client.eval(
                self._SCRIPT,
                1,
                key,
                now_ms,
                window_ms,
                limit,
                member,
            )
        except Exception as exc:
            raise RateLimitBackendError(
                "Shared rate-limit backend is unavailable."
            ) from exc

        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise RateLimitBackendError(
                "Shared rate-limit backend returned an invalid response."
            )

        allowed, retry_after = result
        return RateLimitDecision(bool(int(allowed)), max(0, int(retry_after)))

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


class RateLimiter:
    def __init__(
        self,
        backend: RateLimitBackend,
        policies: Mapping[str, RateLimitPolicy],
        *,
        key_prefix: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._backend = backend
        self._policies = dict(policies)
        self._key_prefix = key_prefix.strip(":")
        self._clock = clock

    def check(self, policy_name: str, client_identifier: str) -> RateLimitDecision:
        try:
            policy = self._policies[policy_name]
        except KeyError as exc:
            raise RateLimitConfigurationError(
                f"Unknown rate-limit policy: {policy_name!r}."
            ) from exc

        digest = hashlib.sha256(client_identifier.encode("utf-8")).hexdigest()
        key = f"{self._key_prefix}:{policy.name}:{digest}"
        try:
            return self._backend.check(
                key, policy.limit, policy.window_seconds, self._clock()
            )
        except RateLimitBackendError:
            raise
        except Exception as exc:
            raise RateLimitBackendError("Rate-limit backend check failed.") from exc

    def close(self) -> None:
        self._backend.close()


def build_policies(settings: Settings) -> dict[str, RateLimitPolicy]:
    return {
        INCIDENTS_CREATE_POLICY: RateLimitPolicy(
            INCIDENTS_CREATE_POLICY,
            settings.rate_limit_incidents_create_limit,
            settings.rate_limit_incidents_create_window_seconds,
        ),
        TRACKING_LOOKUP_POLICY: RateLimitPolicy(
            TRACKING_LOOKUP_POLICY,
            settings.rate_limit_tracking_lookup_limit,
            settings.rate_limit_tracking_lookup_window_seconds,
        ),
        LOGIN_POLICY: RateLimitPolicy(
            LOGIN_POLICY,
            settings.rate_limit_login_limit,
            settings.rate_limit_login_window_seconds,
        ),
        VOICE_TRANSCRIBE_POLICY: RateLimitPolicy(
            VOICE_TRANSCRIBE_POLICY,
            settings.rate_limit_voice_transcribe_limit,
            settings.rate_limit_voice_transcribe_window_seconds,
        ),
        VOICE_SPEAK_POLICY: RateLimitPolicy(
            VOICE_SPEAK_POLICY,
            settings.rate_limit_voice_speak_limit,
            settings.rate_limit_voice_speak_window_seconds,
        ),
        AI_UNDERSTAND_POLICY: RateLimitPolicy(
            AI_UNDERSTAND_POLICY,
            settings.rate_limit_ai_understand_limit,
            settings.rate_limit_ai_understand_window_seconds,
        ),
        AI_ANALYZE_IMAGE_POLICY: RateLimitPolicy(
            AI_ANALYZE_IMAGE_POLICY,
            settings.rate_limit_ai_analyze_image_limit,
            settings.rate_limit_ai_analyze_image_window_seconds,
        ),
    }


def build_rate_limiter(settings: Settings) -> RateLimiter | None:
    """Build the configured limiter, or ``None`` when rate limiting is off."""

    if not settings.rate_limit_enabled:
        return None

    policies = build_policies(settings)

    if settings.rate_limit_backend == "redis":
        url = (settings.rate_limit_redis_url or "").strip()
        if not url:
            raise RateLimitConfigurationError(
                "RATE_LIMIT_REDIS_URL is required when RATE_LIMIT_BACKEND=redis."
            )

        try:
            redis_backend = RedisRateLimitBackend(
                url,
                timeout_seconds=settings.rate_limit_redis_timeout_seconds,
            )
            redis_backend.ping()
        except RateLimitConfigurationError:
            raise
        except RateLimitBackendError:
            if settings.is_production:
                raise
            logger.warning(
                "Shared rate-limit backend is unavailable; using the in-memory "
                "development fallback. This fallback is not multi-worker safe."
            )
            redis_backend.close()
            backend: RateLimitBackend = InMemoryRateLimitBackend()
        else:
            backend = redis_backend
    else:
        if settings.is_production:
            logger.warning(
                "RATE_LIMIT_BACKEND=memory in production is single-process only; "
                "configure Redis for multi-worker deployments."
            )
        backend = InMemoryRateLimitBackend()

    return RateLimiter(
        backend,
        policies,
        key_prefix=settings.rate_limit_key_prefix,
    )


_default_limiter: RateLimiter | None = None
_default_limiter_lock = threading.Lock()


def get_default_rate_limiter() -> RateLimiter | None:
    global _default_limiter
    if _default_limiter is None:
        with _default_limiter_lock:
            if _default_limiter is None:
                _default_limiter = build_rate_limiter(get_settings())
    return _default_limiter


def get_rate_limiter(request: Request) -> RateLimiter | None:
    """Return the app-scoped limiter, or a lazily built default for tests."""
    if getattr(request.app.state, "rate_limit_initialized", False):
        return getattr(request.app.state, "rate_limiter", None)
    return get_default_rate_limiter()


def reset_rate_limiter() -> None:
    """Close and forget the lazily built default limiter (test helper)."""
    global _default_limiter
    with _default_limiter_lock:
        if _default_limiter is not None:
            _default_limiter.close()
        _default_limiter = None


def rate_limit(policy_name: str) -> Callable[..., None]:
    """Build a FastAPI dependency that enforces one configured policy."""

    def dependency(
        request: Request,
        limiter: RateLimiter | None = Depends(get_rate_limiter),
    ) -> None:
        if limiter is None:
            return None

        client_ip = resolve_client_ip(
            request, get_settings().rate_limit_trusted_proxy_networks
        )
        try:
            decision = limiter.check(policy_name, client_ip)
        except RateLimitBackendError as exc:
            logger.error(
                "Rate-limit backend unavailable while checking policy %s",
                policy_name,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Rate limiting is temporarily unavailable. "
                    "Please try again later."
                ),
            ) from exc

        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={
                    "Retry-After": str(max(1, decision.retry_after)),
                    "Cache-Control": "no-store",
                },
            )
        return None

    return dependency
