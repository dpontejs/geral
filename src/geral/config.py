from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-flash-latest"
    RESEND_API_KEY: str | None = None
    # Sender address; the display name is the team's newsletter ("Timbu News <news@...>").
    NEWSLETTER_FROM: str = "news@seudominio.com"
    NEWSLETTER_RECIPIENTS: str | list[str] = ["voce@email.com"]
    TIMEZONE: str = "America/Sao_Paulo"
    DRY_RUN: bool = True
    # Subscription page (slice 2); unused until SUBSCRIBERS_API_TOKEN is set.
    PUBLIC_URL: str = "http://localhost:8000"
    SUBSCRIBE_SECRET: str | None = None  # signs confirmation and unsubscribe links
    SUBSCRIBERS_API_TOKEN: str | None = None  # protects /api/subscribers (and enables it in run)
    SUBSCRIBERS_DB: str = "data/subscribers.db"
    NOTIFY_EMAIL: str | None = None  # gets an e-mail whenever someone confirms a subscription
    # A single-team app that moved in (docs/adr/0001): its sent e-mails keep working. Its tokens
    # (signed with its secret) act on LEGACY_TEAM; its old hosts send the home page to the Geral.
    LEGACY_TEAM: str | None = None
    LEGACY_SUBSCRIBE_SECRET: str | None = None
    LEGACY_HOSTS: str = ""  # comma-separated host names

    @field_validator("NEWSLETTER_RECIPIENTS")
    @classmethod
    def parse_recipients(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [email.strip() for email in v.split(",") if email.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
