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


class GeminiGatewayProvider:
    """
    Thin httpx wrapper around the candidate-facing Gemini Gateway.
    POST /chat with Bearer auth. Returns the assistant's text as a string.
    """

    def __init__(self, base_url: str, secret: str, fast_model: str, smart_model: str):
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._model_by_role = {"fast": fast_model, "smart": smart_model}
        # gemini-2.5-pro can take 30-60s on long prompts; size accordingly.
        self._client = httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0))

    def _resolve(self, role: str) -> str:
        return self._model_by_role.get(role, self._model_by_role["smart"])

    def _post_with_retry(self, body: dict, headers: dict, max_attempts: int = 4) -> dict:
        url = f"{self._base_url}/chat"
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
                        "gemini gateway %s on attempt %d/%d; sleeping %.1fs",
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
                    "gemini gateway transport error on attempt %d/%d (%s); sleeping %.1fs",
                    attempt, max_attempts, type(exc).__name__, delay,
                )
                time.sleep(delay)
        if last_exc:
            raise last_exc
        raise RuntimeError("gemini gateway: retries exhausted")

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
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._secret}",
            "Content-Type": "application/json",
        }
        data = self._post_with_retry(body, headers)
        # Gateway returns the assistant text in common shapes; be permissive.
        if isinstance(data, dict):
            for key in ("reply", "response", "content", "text", "message", "output"):
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    return v
            # Anthropic-style content blocks
            content = data.get("content")
            if isinstance(content, list):
                parts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") in (None, "text")
                ]
                joined = "".join(parts).strip()
                if joined:
                    return joined
            # OpenAI-style choices
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                if isinstance(msg, dict):
                    c = msg.get("content")
                    if isinstance(c, str):
                        return c
        logger.warning("Gemini Gateway returned unexpected shape: %r", str(data)[:300])
        return ""


class AnthropicProvider:
    """
    Preserved so the system is genuinely provider-agnostic. Lazily imports the
    SDK so installs without the anthropic package still work when Gemini is
    selected.
    """

    def __init__(self, api_key: str, fast_model: str, smart_model: str):
        from anthropic import Anthropic  # noqa: WPS433

        self._client = Anthropic(api_key=api_key)
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
        resp = self._client.messages.create(
            model=self._resolve(role),
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    name = (settings.llm_provider or "gemini_gateway").lower()
    if name == "anthropic":
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            fast_model=settings.anthropic_fast_model,
            smart_model=settings.anthropic_model,
        )
    return GeminiGatewayProvider(
        base_url=settings.gemini_gateway_url,
        secret=settings.gemini_gateway_secret,
        fast_model=settings.gemini_fast_model,
        smart_model=settings.gemini_smart_model,
    )
