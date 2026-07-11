from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    environment: str = "development"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Database
    database_url: str = "postgresql+asyncpg://dh:dh@db:5432/dh"
    test_database_url: str = "sqlite+aiosqlite:///./test.db"

    # CORS
    frontend_origin: str = "http://localhost:5173"

    # Media
    media_root: str = "/app/media"
    media_url: str = "/media"

    # File limits
    max_image_size_bytes: int = 10 * 1024 * 1024
    max_track_file_size_bytes: int = 5 * 1024 * 1024

    # Result auto-validation tolerances
    result_distance_tolerance_pct: float = 10.0
    result_start_time_tolerance_minutes: int = 60

    # Email — Yandex SMTP (see .env.example for how to obtain an app password)
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = "smtp.yandex.ru"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "DАЙ ХАРD <no-reply@yandex.ru>"

    # SQLAdmin
    admin_secret_key: str = "change-me-too"

    # Initial admin bootstrap
    initial_admin_email: str = "admin@example.com"
    initial_admin_password: str = "change-me-admin-password"

    @property
    def allowed_image_extensions(self) -> set[str]:
        return {".jpg", ".jpeg", ".png", ".webp"}

    @property
    def allowed_track_extensions(self) -> set[str]:
        return {".gpx", ".fit"}


_INSECURE_DEFAULTS = {
    "secret_key": "change-me",
    "admin_secret_key": "change-me-too",
    "initial_admin_password": "change-me-admin-password",
}
_MIN_SECRET_LENGTH = 32


def _assert_production_is_configured(s: Settings) -> None:
    """Fail fast at startup instead of silently running production with dev
    secrets — a leftover default here means forged JWTs or a public admin
    password, not just a config typo."""
    if s.environment != "production":
        return
    reused_defaults = [
        name for name, default in _INSECURE_DEFAULTS.items() if getattr(s, name) == default
    ]
    if reused_defaults:
        raise RuntimeError(
            "Refusing to start with ENVIRONMENT=production while these settings "
            f"still have their insecure default value: {', '.join(reused_defaults)}. "
            "Set real values in the deployment .env."
        )
    too_short = [
        name
        for name in ("secret_key", "admin_secret_key")
        if len(getattr(s, name)) < _MIN_SECRET_LENGTH
    ]
    if too_short:
        raise RuntimeError(
            f"Refusing to start with ENVIRONMENT=production: {', '.join(too_short)} "
            f"must be at least {_MIN_SECRET_LENGTH} random characters "
            "(e.g. `openssl rand -hex 32`)."
        )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _assert_production_is_configured(s)
    return s


settings = get_settings()
