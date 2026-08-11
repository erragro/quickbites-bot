"""
Language detection — a single lightweight Google Cloud Translation API v2
call, run once per turn before Stage 0. Deliberately not folded into Stage
0's classification prompt: Translation's dedicated detect endpoint is a
fast, cheap REST call, not a generative one, so this doesn't add meaningful
latency to the pipeline.

Routing consumes the ISO-639 code this returns: `en`/`hi` stay on Gemini,
anything else routes to Sarvam AI (see llm_provider.get_provider).
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

_ENDPOINT = "https://translation.googleapis.com/language/translate/v2/detect"

# Languages Gemini handles directly; everything else routes to Sarvam.
GEMINI_LANGUAGES = {"en", "hi"}

LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "gu": "Gujarati",
    "pa": "Punjabi", "bn": "Bengali", "or": "Odia", "ur": "Urdu",
}


def detect(text: str) -> str:
    """Returns an ISO-639 language code. Falls back to 'en' on any failure —
    a wrong guess here should degrade to the current behavior, never crash
    the turn."""
    if not text or not text.strip():
        return "en"
    if not settings.google_translate_api_key:
        logger.warning("GOOGLE_TRANSLATE_API_KEY not set; defaulting to en")
        return "en"
    try:
        resp = httpx.post(
            _ENDPOINT,
            params={"key": settings.google_translate_api_key},
            json={"q": text},
            timeout=httpx.Timeout(5.0, connect=3.0),
        )
        resp.raise_for_status()
        detections = resp.json()["data"]["detections"]
        code = detections[0][0]["language"]
        return code.split("-")[0].lower()
    except Exception:  # noqa: BLE001
        logger.warning("language detection failed; defaulting to en", exc_info=True)
        return "en"
