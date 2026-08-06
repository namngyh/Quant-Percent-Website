from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # Origins allowed to call the API with credentials.
    # NoDecode keeps pydantic-settings from JSON-parsing the raw value, so the
    # documented comma-separated form reaches _split_origins below. Without it
    # any CORS_ORIGINS that is not valid JSON aborts startup.
    cors_origins: Annotated[list[str], NoDecode] = Field(
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
    # Two ways to send. Resend needs a verified sending domain; SMTP works
    # with an ordinary mailbox and no DNS changes. Resend wins when both are
    # configured. With neither, mail is skipped and nothing else breaks.
    resend_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    # Port 465 speaks TLS from the first byte; 587 upgrades with STARTTLS.
    smtp_use_ssl: bool = False
    email_from: str = "Quant Percent <noreply@quantpercent.com>"
    contact_notify_email: str | None = None
    public_site_url: str = "http://localhost:3000"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    # --- Data --------------------------------------------------------------
    # Publication delay in minutes, reported on every market payload.
    #
    # This defaulted to 15 while nothing enforced it: the API announced a
    # 15-minute delay and served the newest bar anyway, roughly a minute old.
    # Measured 2026-08-05 — bar 14:25 was queryable at 14:26:01.
    #
    # Withholding recent rows is not implemented. Until it is, this value must
    # stay 0, and `_check_delay_is_enforceable` below refuses to boot with any
    # other value rather than let the number on the page drift from the data
    # behind it again.
    market_delay_minutes: int = 0
    # A feed older than this is reported as stale.
    stale_after_minutes: int = 90

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _check_delay_is_enforceable(self) -> "Settings":
        """A declared delay nobody applies is worse than no delay at all.

        Someone reading "delayed 15 minutes" is entitled to assume the data is
        15 minutes old. Fail loudly instead of shipping that claim unbacked.
        """
        if self.market_delay_minutes != 0:
            raise ValueError(
                "MARKET_DELAY_MINUTES must be 0: withholding recent rows is "
                "not implemented, so any other value would advertise a delay "
                "the API does not apply. Implement the cutoff in the market "
                "queries first, then raise this."
            )
        return self

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
