"""
Application settings, loaded from environment variables.

Per the Security Audit reconciliation (Module 11) and the original API
Design doc, secrets are never hardcoded — this module is the single place
that reads them from the environment, so nothing else in the codebase
touches `os.environ` directly.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM provider
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"

    # Database (used by later modules, included now for completeness)
    database_url: str = "postgresql://localhost:5432/vachanai"

    # Extraction tuning
    extraction_max_tokens: int = 500
    extraction_temperature: float = 0.0  # deterministic classification, not creative generation

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — avoids re-reading the environment on every call."""
    return Settings()
