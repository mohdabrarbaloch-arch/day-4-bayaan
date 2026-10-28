"""Runtime configuration. Everything comes from the environment — nothing is hardcoded."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_serverless() -> bool:
    """Vercel / Lambda give us a read-only project dir, so SQLite must live in /tmp."""
    return bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def _default_database_url() -> str:
    if _detect_serverless():
        return "sqlite:////tmp/bayaan.db"
    return "sqlite:///./bayaan.db"


class Settings(BaseSettings):
    """Application settings, loaded from env vars and an optional .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Bayaan"
    environment: str = "development"
    debug: bool = False

    # --- auth -----------------------------------------------------------------
    # Never ship the default. Production refuses to boot without a real key.
    secret_key: str = "dev-only-insecure-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # --- storage --------------------------------------------------------------
    database_url: str = _default_database_url()

    # --- inference backends ---------------------------------------------------
    # `ollama_base_url` turns on the real local backend: models running on your
    # own machine via Ollama. Leave it empty and local mode falls back to the
    # built-in dry-run inspector, which is labelled as such everywhere in the UI.
    ollama_base_url: str = ""
    ollama_timeout_seconds: float = 120.0

    # Any OpenAI-compatible endpoint (OpenAI, Groq, Together, vLLM, LM Studio...).
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_api_key: str = ""
    cloud_timeout_seconds: float = 120.0

    # --- web ------------------------------------------------------------------
    cors_origins: str = "*"
    # Hostnames TrustedHostMiddleware accepts in production. Comma-separated.
    allowed_hosts: str = "localhost,127.0.0.1"
    rate_limit_runs: str = "30/minute"
    rate_limit_auth: str = "10/minute"
    max_prompt_chars: int = 20000

    # Example list prices per 1M tokens. Edit these to match the provider you
    # actually point the cloud backend at, otherwise cost figures are fiction.
    price_input_per_mtok: float = 0.15
    price_output_per_mtok: float = 0.60

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        hosts = [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
        return hosts or ["*"]

    @property
    def cloud_enabled(self) -> bool:
        return bool(self.cloud_api_key)

    @property
    def ollama_enabled(self) -> bool:
        return bool(self.ollama_base_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
