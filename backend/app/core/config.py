from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Everything comes from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---------------------------------------------------------------
    app_name: str = "Quant Percent API"
    environment: Literal["dev", "staging", "production"] = "dev"
    # Use a project-specific env name. Generic DEBUG is commonly injected by
    # hosting/build environments with non-boolean values such as "release".
    debug: bool = Field(default=False, validation_alias="QP_DEBUG")
    api_prefix: str = "/api/v1"

    # Origins allowed to call the API with credentials
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # --- Database ----------------------------------------------------------
    # The web role. It may read the vetted `api` views and own `web`;
    # it deliberately has no rights on the ingestion schema.
    database_url: str = "postgresql+asyncpg://qp_web:change-me@localhost:5432/market"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False

    # --- Redis -------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/1"

    # --- Auth --------------------------------------------------------------
    # Long enough for HS256 even in development, so tests exercise a
    # realistic key size
    jwt_secret: str = "dev-only-change-me-0123456789abcdef0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_domain: str | None = None
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    access_cookie_name: str = "qp_access"
    refresh_cookie_name: str = "qp_refresh"
    csrf_cookie_name: str = "qp_csrf"

    # --- Email (optional; submissions are stored regardless) ---------------
    resend_api_key: str | None = None
    email_from: str = "Quant Percent <noreply@quantpercent.com>"
    contact_notify_email: str | None = None
    public_site_url: str = "http://localhost:3000"

    # --- Data --------------------------------------------------------------
    # Delay we are contractually allowed to publish market data with.
    market_delay_minutes: int = 15
    # A feed older than this is reported as stale.
    stale_after_minutes: int = 90

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        """Refuse to boot production with development defaults.

        HS256 needs at least 32 bytes of key material, and the sample
        secret is public in .env.example.
        """
        if self.environment == "production":
            if len(self.jwt_secret) < 32 or "change-me" in self.jwt_secret:
                raise ValueError(
                    "JWT_SECRET must be a unique value of at least 32 characters "
                    "in production"
                )
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
