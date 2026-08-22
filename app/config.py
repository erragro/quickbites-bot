from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# pydantic-settings' env_file= below loads .env into this Settings object,
# but Google's auth library reads GOOGLE_APPLICATION_CREDENTIALS straight
# from os.environ, bypassing our Settings entirely — so .env has to also be
# loaded into the real process environment, not just parsed by pydantic.
load_dotenv(PROJECT_ROOT / ".env")
DATA_TODAY = date(2026, 4, 13)
POLICY_FAQ_PATH = PROJECT_ROOT / "policy_and_faq.md"
SQLITE_SEED_PATH = PROJECT_ROOT / "data" / "app.db"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://quickbites:quickbites@localhost:5432/quickbites"

    # Logical model roles; each provider maps them to a concrete model id.
    model_fast: str = "fast"      # used by Stage 0 classifier
    model_smart: str = "smart"    # used by Stage 1 evaluator + Stage 3 responder

    # Provider routing is automatic, by detected language (see
    # language_detector.py + llm_provider.get_provider) — en/hi → Gemini,
    # everything else → Sarvam. No manual provider toggle.

    # Gemini — supports two auth paths, chosen at runtime by which env
    # var is set:
    #   1. GEMINI_API_KEY (Google AI Studio, https://aistudio.google.com/apikey)
    #      — bare API key, no Google Cloud project needed. Simplest for
    #      local dev + demos.
    #   2. GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT
    #      (Vertex AI). Service-account JSON, or ADC via
    #      `gcloud auth application-default login`. Required in prod
    #      when you want VPC-SC, IAM, or Vertex-only models.
    # If GEMINI_API_KEY is set it wins. Otherwise Vertex is attempted.
    gemini_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "asia-south1"
    gemini_fast_model: str = "gemini-2.5-flash-lite"
    gemini_smart_model: str = "gemini-2.5-flash"

    # Sarvam AI (all other Indian languages). Model naming as of 2026-08:
    # sarvam-105b is the reasoning model (emits reasoning_content and eats
    # into max_tokens); sarvam-105b-conversations is the non-thinking
    # variant that returns directly. Default to conversations for both
    # roles because Sarvam's starter tier caps completion tokens at 4096
    # and the reasoning burns most of that on internal chain-of-thought.
    sarvam_api_key: str = ""
    sarvam_fast_model: str = "sarvam-105b-conversations"
    sarvam_smart_model: str = "sarvam-105b-conversations"
    # Ceiling for max_tokens in Sarvam requests. Starter subscription cap
    # is 4096; requests above this get rejected with a 400. The provider
    # clamps every call to this ceiling so callers can pass their own
    # ideal budget without knowing the subscription tier.
    sarvam_max_tokens_cap: int = 4096

    # Google Cloud Translation API v2 (Basic) — language detection only
    google_translate_api_key: str = ""

    simulator_base_url: str = "http://localhost:8000"
    candidate_token: str = "demo"

    refund_soft_cap_inr: int = 1500
    confidence_floor: float = 0.6
    dedup_ttl_seconds: int = 600

    # -- Auth ----------------------------------------------------------------
    # JWT secret MUST be overridden in every environment via env var. The
    # default value here is a marker string; app boot refuses to run with it
    # in prod (see main.py startup guard).
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_this_default_is_unsafe"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60 * 24        # 24h — matches session UX
    jwt_issuer: str = "quickbites"
    password_min_length: int = 8
    # slowapi limits — string form because slowapi parses these
    auth_signup_rate: str = "10/hour"
    auth_login_rate: str = "30/hour"

    # Super-admin bootstrap. If set, the first signup that matches this
    # email becomes super_admin. If not set, the very first user to sign
    # up becomes super_admin (single-tenant / demo mode).
    super_admin_email: str = ""

    # Newly signed-up users get 'view' access to these module keys by
    # default so the demo works out of the box. Comma-separated env var.
    default_module_keys: str = "chatbot,contract_reader,rights_guide,schemes_finder,complaint_helper"

    # -- Contract Reader storage --------------------------------------------
    # Where uploaded contract files live. Local dev writes to a repo-relative
    # path; prod (Cloud Run) overrides via env var to a GCS bucket path.
    # See app/contracts/storage.py — LocalStorage prefixes this root, GCS
    # variant treats it as bucket name + prefix.
    contract_storage_root: str = "./data/contracts"
    contract_max_bytes: int = 10 * 1024 * 1024  # 10 MB

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
