"""App configuration, loaded from environment variables (and .env in dev).

Nothing here has a fallback for anything security- or connectivity-sensitive
(DATABASE_URL, JWT_SECRET) - if they're missing, the app should fail to boot
rather than silently start up with a useless default.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- database ---
    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # --- auth ---
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- cors / deployment ---
    cors_allow_origins: list[str] = ["*"]
    # Starlette's TrustedHostMiddleware. "*" (the default) disables the check -
    # set this to your real domain(s) in production so requests with a
    # forged/mismatched Host header get rejected before they reach a route.
    allowed_hosts: list[str] = ["*"]
    environment: str = "development"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Managed Postgres providers (Railway, Heroku-style addons) hand out
        # DATABASE_URL as "postgres://..." or "postgresql://...", which
        # SQLAlchemy resolves to psycopg2 by default. We install psycopg v3
        # instead, so rewrite the scheme to say so explicitly - one less
        # thing to get wrong copy-pasting a provider's connection string.
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://") :]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
