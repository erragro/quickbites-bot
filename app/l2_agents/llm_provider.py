"""
LLM provider abstraction — keeps the 4-stage pipeline decoupled from any
single vendor SDK. The only call-site contract is `chat(...)` returning the
raw text of the assistant turn. Structured-JSON parsing stays in each stage.

Model roles:
  - "fast"  → cheap classifier (Stage 0)
  - "smart" → judgment + response (Stage 1, Stage 3)
"""

from __future__ import annotations

import json
import logging
import random
import time
from functools import lru_cache
from typing import Iterator, Protocol

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

    def chat_stream(
        self,
        *,
        role: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Yield response text chunks as they arrive. Not every stage needs
        this — the callers that do (Stage 3 responder) use it to stream
        tokens to the client via SSE. Stage 0 / Stage 1 stay on chat()
        because they parse structured JSON and can't emit partials."""
        ...


class VertexAIProvider:
    """
    Calls Gemini through either:
      - Google AI Studio (bare API key, GEMINI_API_KEY env var) — simplest;
        chosen automatically when settings.gemini_api_key is set.
      - Vertex AI (google-genai SDK, vertexai=True) — needs Application
        Default Credentials (GOOGLE_APPLICATION_CREDENTIALS to a
        service-account JSON, or `gcloud auth application-default login`)
        plus GOOGLE_CLOUD_PROJECT with Vertex AI enabled + active billing.

    Class name stays `VertexAIProvider` for import stability; the docstring
    is the single source of truth on what it actually does.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        project: str = "",
        location: str = "",
        fast_model: str,
        smart_model: str,
    ):
        from google import genai  # noqa: WPS433

        # Preference: Vertex (project + ADC) whenever a project is set,
        # because setup_adc.sh implicitly enables Vertex AI on the project,
        # and Vertex works cleanly with quota + IAM in production. Fall
        # back to AI Studio (bare API key) only if no project is available.
        if project:
            self._client = genai.Client(
                vertexai=True, project=project, location=location,
            )
            self._auth_mode = "vertex"
        elif api_key:
            self._client = genai.Client(api_key=api_key)
            self._auth_mode = "ai_studio"
        else:
            raise RuntimeError(
                "Gemini provider needs either GOOGLE_CLOUD_PROJECT (Vertex + ADC) "
                "or GEMINI_API_KEY (AI Studio)."
            )
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

        # Gemini 2.5-family "thinking" adds 5-15s per Stage 1/3 call and
        # buys us nothing here — deterministic Stage 2 validates every
        # action set the LLM proposes anyway, so extra internal reasoning
        # is a latency tax on decisions we then override in Python.
        # thinking_budget=0 turns it off. flash-lite ignores this
        # (thinking is off by default there), flash + pro honour it.
        thinking_off = types.ThinkingConfig(thinking_budget=0)

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            thinking_config=thinking_off,
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

    def chat_stream(
        self,
        *,
        role: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Streams text chunks via the google-genai SDK's server-sent
        streaming endpoint. Skips retry — the client is holding a
        real-time SSE connection open and a mid-stream retry would
        replay tokens the user already saw. On failure we let the
        exception bubble; the pipeline degrades to escalate."""
        from google.genai import types  # noqa: WPS433

        model = self._resolve(role)
        thinking_off = types.ThinkingConfig(thinking_budget=0)
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            thinking_config=thinking_off,
        )

        stream = self._client.models.generate_content_stream(
            model=model, contents=user, config=config,
        )
        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text


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
                if resp.status_code == 400:
                    # Log the body so we can see the actual rejection
                    # reason (model deprecated, max_tokens too high,
                    # message too long, etc). The HTTPStatusError below
                    # doesn't include the response body by default.
                    logger.error(
                        "sarvam 400: model=%s max_tokens=%s response=%s",
                        body.get("model"),
                        body.get("max_tokens"),
                        resp.text[:800],
                    )
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
            # Clamp to the subscription-tier cap. Starter tier is 4096;
            # requests above that fail with a 400 "exceeds subscription
            # tier limit". Callers can safely pass their preferred budget
            # (e.g. 8192 for Stage 1/3) without knowing the tier.
            "max_tokens": min(max_tokens, settings.sarvam_max_tokens_cap),
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
            if isinstance(content, str) and content.strip():
                return content
            # Reasoning models (sarvam-105b, not -conversations) may
            # return content=null when max_tokens ran out on internal
            # reasoning_content. Fall back to that so downstream parsers
            # at least get something to work with, even if malformed.
            reasoning = msg.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning.strip():
                logger.warning(
                    "Sarvam returned reasoning_content only (content was empty). "
                    "Switch to sarvam-105b-conversations for cleaner output."
                )
                return reasoning
        logger.warning("Sarvam returned unexpected shape: %r", str(data)[:300])
        return ""

    def chat_stream(
        self,
        *,
        role: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Sarvam ships an OpenAI-compatible streaming SSE endpoint. We
        POST with stream=true, iterate over `data: {...}` frames, and
        yield the delta content of each. Same no-retry policy as the
        Vertex stream — the client is holding a real-time connection."""
        body = {
            "model": self._resolve(role),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        url = "https://api.sarvam.ai/v1/chat/completions"
        with self._client.stream("POST", url, json=body, headers=headers) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines():
                if not raw or not raw.startswith("data: "):
                    continue
                payload = raw[len("data: "):]
                if payload.strip() == "[DONE]":
                    break
                try:
                    frame = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = frame.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield text


@lru_cache(maxsize=4)
def get_provider(language: str = "en") -> LLMProvider:
    """Return the LLM provider for the given language.

    Architecture (as of the Sreshtha pivot, 2026-08-15):
      - Gemini owns ALL analysis + reasoning + generation across every
        language. Gemini 2.5 Flash handles Hindi, Bengali, Tamil, Telugu,
        Kannada, Marathi natively at production quality, and gives us
        consistent tone control from one prompt.
      - Sarvam is now dedicated to two separate purposes: Mayura v1 for
        cross-language translation (see app/translate/sarvam_mayura.py)
        and their transliteration endpoint for Roman ↔ Devanagari script
        flipping (form-time toggle before uploading a contract).
        Neither uses this chat-completions abstraction.

    The `language` argument is kept in the signature for future
    fine-grained routing (e.g. long-context per language) but currently
    every call routes to Gemini.
    """
    _ = language  # reserved for future language-specific model choices
    return VertexAIProvider(
        api_key=settings.gemini_api_key,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        fast_model=settings.gemini_fast_model,
        smart_model=settings.gemini_smart_model,
    )
