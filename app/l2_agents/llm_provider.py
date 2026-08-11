"""
LLM provider abstraction — keeps the 4-stage pipeline decoupled from any
single vendor SDK. The only call-site contract is `chat(...)` returning the
raw text of the assistant turn. Structured-JSON parsing stays in each stage.

Model roles:
  - "fast"  → cheap classifier (Stage 0)
  - "smart" → judgment + response (Stage 1, Stage 3)
"""

from __future__ import annotations

import logging
import random
import time
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    def chat(
        self,
        *,
        role: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str: ...


class VertexAIProvider:
    """
    Calls Gemini directly through Vertex AI (google-genai SDK, vertexai=True)
    — no intermediate proxy service. Authenticates via standard Google
    Application Default Credentials: set GOOGLE_APPLICATION_CREDENTIALS to a
    service-account key file, or run `gcloud auth application-default login`
    for local dev. Requires GOOGLE_CLOUD_PROJECT to have Vertex AI enabled
    and billing active.
    """

    def __init__(self, project: str, location: str, fast_model: str, smart_model: str):
        from google import genai  # noqa: WPS433

        self._client = genai.Client(vertexai=True, project=project, location=location)
        self._model_by_role = {"fast": fast_model, "smart": smart_model}

    def _resolve(self, role: str) -> str:
        return self._model_by_role.get(role, self._model_by_role["smart"])

    def chat(
        self,
        *,
        role: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        from google.genai import types  # noqa: WPS433
        from google.genai import errors  # noqa: WPS433

        model = self._resolve(role)
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        max_attempts = 4
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.models.generate_content(
                    model=model, contents=user, config=config,
                )
                return resp.text or ""
            except errors.APIError as exc:
                last_exc = exc
                status = getattr(exc, "code", None)
                if status == 429 or (status and 500 <= status < 600):
                    delay = min(16.0, (2 ** attempt) + random.uniform(0, 1))
                    logger.warning(
                        "vertex ai %s on attempt %d/%d; sleeping %.1fs",
                        status, attempt, max_attempts, delay,
                    )
                    time.sleep(delay)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("vertex ai: retries exhausted")


class SarvamProvider:
    """
    Sarvam AI's OpenAI-compatible chat completions endpoint. Used for every
    detected language outside Gemini's {en, hi} — see language_detector.py
    for the routing rule.
    """

    def __init__(self, api_key: str, fast_model: str, smart_model: str):
        self._api_key = api_key
        self._model_by_role = {"fast": fast_model, "smart": smart_model}
        self._client = httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))

    def _resolve(self, role: str) -> str:
        return self._model_by_role.get(role, self._model_by_role["smart"])

    def _post_with_retry(self, body: dict, headers: dict, max_attempts: int = 4) -> dict:
        url = "https://api.sarvam.ai/v1/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.post(url, json=body, headers=headers)
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    retry_after = resp.headers.get("retry-after")
                    if retry_after and retry_after.isdigit():
                        delay = min(20.0, float(retry_after))
                    else:
                        delay = min(16.0, (2 ** attempt) + random.uniform(0, 1))
                    logger.warning(
                        "sarvam %s on attempt %d/%d; sleeping %.1fs",
                        resp.status_code, attempt, max_attempts, delay,
                    )
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                delay = min(16.0, (2 ** attempt) + random.uniform(0, 1))
                logger.warning(
                    "sarvam transport error on attempt %d/%d (%s); sleeping %.1fs",
                    attempt, max_attempts, type(exc).__name__, delay,
                )
                time.sleep(delay)
        if last_exc:
            raise last_exc
        raise RuntimeError("sarvam: retries exhausted")

    def chat(
        self,
        *,
        role: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        body = {
            "model": self._resolve(role),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        data = self._post_with_retry(body, headers)
        choices = data.get("choices") if isinstance(data, dict) else None
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                return content
        logger.warning("Sarvam returned unexpected shape: %r", str(data)[:300])
        return ""


@lru_cache(maxsize=4)
def get_provider(language: str = "en") -> LLMProvider:
    from app.l2_agents.language_detector import GEMINI_LANGUAGES

    if language in GEMINI_LANGUAGES:
        return VertexAIProvider(
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            fast_model=settings.gemini_fast_model,
            smart_model=settings.gemini_smart_model,
        )
    return SarvamProvider(
        api_key=settings.sarvam_api_key,
        fast_model=settings.sarvam_fast_model,
        smart_model=settings.sarvam_smart_model,
    )
