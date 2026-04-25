from datetime import date
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_TODAY = date(2026, 4, 13)
POLICY_FAQ_PATH = PROJECT_ROOT / "policy_and_faq.md"
SQLITE_SEED_PATH = PROJECT_ROOT / "data" / "app.db"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://quickbites:quickbites@localhost:5432/quickbites"

    # Provider selection: "gemini_gateway" or "anthropic".
    llm_provider: str = "gemini_gateway"

    # Logical model roles; each provider maps them to a concrete model id.
    model_fast: str = "fast"      # used by Stage 0 classifier
    model_smart: str = "smart"    # used by Stage 1 evaluator + Stage 3 responder

    # Gemini Gateway
    gemini_gateway_url: str = "https://gemini-gateway-162392320588.asia-south1.run.app"
    gemini_gateway_secret: str = ""
    gemini_fast_model: str = "gemini-2.5-flash-lite"
    gemini_smart_model: str = "gemini-2.5-flash"

    # Anthropic (preserved for provider-agnostic operation)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_fast_model: str = "claude-haiku-4-5"

    simulator_base_url: str = "http://localhost:8000"
    candidate_token: str = "demo"

    refund_soft_cap_inr: int = 1500
    confidence_floor: float = 0.6
    dedup_ttl_seconds: int = 600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
