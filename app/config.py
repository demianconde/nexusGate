"""Configuração central da aplicação, carregada de variáveis de ambiente / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    env: str = Field(default="development", alias="NEXUS_ENV")
    port: int = Field(default=8000, alias="NEXUS_PORT")
    log_level: str = Field(default="INFO", alias="NEXUS_LOG_LEVEL")
    log_json: bool = Field(default=False, alias="NEXUS_LOG_JSON")

    # Infra
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/nexusgate",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Supabase (Fase 1)
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")

    # Envelope encryption (Fase 2)
    master_key: str | None = Field(default=None, alias="NEXUS_MASTER_KEY")

    # Stripe (Fase 5)
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância única de Settings (cacheada)."""
    return Settings()
