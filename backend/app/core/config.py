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
    # LLM provider — Groq (OpenAI-compatible API), chosen for demo-scope
    # ease of access (free tier, fast to get an API key) over Anthropic/OpenAI
    # directly. openai/gpt-oss-120b is Groq's current recommended flagship
    # open-weight model as of July 2026 (their prior Llama 3.x models were
    # deprecated in June 2026) — see ADR log for this swap's reasoning.
    groq_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"

    # Database — SQLite for the 8-day demo scope (Reconciliation Addendum-
    # adjacent decision: production design uses PostgreSQL, but SQLite
    # needs zero setup and persists to a single file, which is what a
    # live demo actually needs). Swap to a Postgres URL here when Phase 2+
    # infrastructure is actually stood up — no code elsewhere needs to change,
    # since SQLAlchemy abstracts the dialect.
    database_url: str = "sqlite:///./vachanai_demo.db"

    # Extraction tuning
    extraction_max_tokens: int = 500
    extraction_temperature: float = 0.0  # deterministic classification, not creative generation

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — avoids re-reading the environment on every call."""
    return Settings()
