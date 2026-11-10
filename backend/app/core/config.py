from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.network import IPNetwork, parse_trusted_proxy_networks

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
# repository root (contains frontend/, backend/, docs/)
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env files."""

    model_config = SettingsConfigDict(
        # Root .env is shared with Vite (see frontend/vite.config.js).
        # backend/.env, when present, takes precedence.
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "CivicPulse AI API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # MySQL
    # Prefer a complete SQLAlchemy URL (read from DATABASE_URL). The DB_*
    # fields remain as a fallback for local setups.
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "civicpulse"
    db_password: str = ""
    db_name: str = "civicpulse"

    # Gnani AI — values are intentionally generic placeholders.
    # Endpoint paths and auth formats must come from official Gnani docs.
    gnani_base_url: str = ""
    gnani_api_key: str = ""

    # Gnani Prisma speech-to-text (official REST contract).
    # https://docs.gnani.ai/api/STT/speech-to-text
    gnani_stt_url: str = "https://api.vachana.ai/stt/v3"
    gnani_stt_model: str = "prisma-v3.0"
    gnani_stt_language_code: str = "indic-auto"
    gnani_stt_timeout_seconds: float = 60.0
    gnani_stt_max_upload_mb: int = Field(default=10, ge=1, le=100)

    # Gnani Timbre text-to-speech (official REST contract).
    # https://docs.gnani.ai/api/TTS/tts-inference
    gnani_tts_base_url: str = "https://api.vachana.ai"
    gnani_tts_model: str = "timbre-v2.5"
    gnani_tts_timeout_seconds: float = 60.0

    # YOLO
    yolo_model_path: str = "yolov8n.pt"
    yolo_confidence: float = 0.35
    yolo_max_upload_mb: int = Field(default=10, ge=1, le=100)
    yolo_max_image_width: int = Field(default=8192, ge=1, le=100_000)
    yolo_max_image_height: int = Field(default=8192, ge=1, le=100_000)
    yolo_max_image_pixels: int = Field(
        default=25_000_000, ge=1, le=1_000_000_000
    )
    yolo_max_concurrency: int = Field(default=2, ge=1, le=32)

    # Local media storage (not wired to the API yet)
    upload_dir: Path = BACKEND_DIR / "uploads"

    # ---- Authentication / sessions ----
    # Cookies are opaque session handles. The server stores only SHA-256
    # hashes, so no shared cookie-signing secret is required.
    auth_cookie_name: str = "civicpulse_session"
    csrf_cookie_name: str = "civicpulse_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    session_ttl_minutes: int = Field(default=480, ge=5, le=43200)
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)

    # ---- Rate limiting / abuse protection ----
    # The default memory backend is per-process and intended for local
    # development or a single worker. Multi-worker production deployments
    # should set RATE_LIMIT_BACKEND=redis and install requirements-redis.txt.
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_redis_url: str | None = None
    rate_limit_redis_timeout_seconds: float = Field(default=1.0, gt=0, le=30)
    rate_limit_key_prefix: str = Field(
        default="civicpulse:ratelimit", min_length=1, max_length=100
    )
    # Comma-separated IPs/CIDRs whose X-Forwarded-For/X-Real-IP headers may be
    # trusted. Leave empty when the app is not behind a reverse proxy.
    rate_limit_trusted_proxies: str = ""

    rate_limit_incidents_create_limit: int = Field(default=5, ge=1, le=100_000)
    rate_limit_incidents_create_window_seconds: int = Field(
        default=600, ge=1, le=86_400
    )
    rate_limit_tracking_lookup_limit: int = Field(default=30, ge=1, le=100_000)
    rate_limit_tracking_lookup_window_seconds: int = Field(
        default=60, ge=1, le=86_400
    )
    rate_limit_login_limit: int = Field(default=30, ge=1, le=100_000)
    rate_limit_login_window_seconds: int = Field(default=60, ge=1, le=86_400)
    rate_limit_voice_transcribe_limit: int = Field(default=10, ge=1, le=100_000)
    rate_limit_voice_transcribe_window_seconds: int = Field(
        default=60, ge=1, le=86_400
    )
    rate_limit_voice_speak_limit: int = Field(default=20, ge=1, le=100_000)
    rate_limit_voice_speak_window_seconds: int = Field(
        default=60, ge=1, le=86_400
    )
    rate_limit_ai_understand_limit: int = Field(default=30, ge=1, le=100_000)
    rate_limit_ai_understand_window_seconds: int = Field(
        default=60, ge=1, le=86_400
    )
    rate_limit_ai_analyze_image_limit: int = Field(default=10, ge=1, le=100_000)
    rate_limit_ai_analyze_image_window_seconds: int = Field(
        default=60, ge=1, le=86_400
    )

    @field_validator("cookie_samesite")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict or none.")
        return normalized

    @field_validator("rate_limit_trusted_proxies")
    @classmethod
    def validate_rate_limit_trusted_proxies(cls, value: str) -> str:
        networks = parse_trusted_proxy_networks(value)
        return ",".join(str(network) for network in networks)

    @model_validator(mode="after")
    def validate_rate_limit_configuration(self) -> "Settings":
        if self.rate_limit_backend == "redis" and not (
            self.rate_limit_redis_url or ""
        ).strip():
            raise ValueError(
                "RATE_LIMIT_REDIS_URL is required when RATE_LIMIT_BACKEND=redis."
            )
        if self.is_production and not self.rate_limit_enabled:
            raise ValueError(
                "RATE_LIMIT_ENABLED cannot be disabled in production."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def rate_limit_trusted_proxy_networks(self) -> tuple[IPNetwork, ...]:
        return parse_trusted_proxy_networks(self.rate_limit_trusted_proxies)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_cookie_secure(self) -> bool:
        """Force Secure cookies in production unless explicitly disabled."""
        return self.cookie_secure or self.environment.strip().lower() in {
            "production",
            "prod",
        }

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return DATABASE_URL when set, otherwise build it from DB_* values."""
        if self.database_url:
            url = self.database_url.strip()
            if url.startswith("mysql://"):
                url = f"mysql+pymysql://{url.removeprefix('mysql://')}"
            return url

        password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
