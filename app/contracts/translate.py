"""Sarvam Mayura v1 translator for Stage 3 output.

Gemini owns all reasoning (Stages 1-3) in English. This module translates
the finished English strings — explanation, implication, action — into
the worker's chosen target language via Sarvam Mayura, which is
purpose-built for Indic translation.

Chunking
--------
Every translate flow batches multiple rows into a single Mayura call
under the input character cap. On a 94-clause Zepto contract this
converts 94 sequential rate-limited calls (~11 minutes end-to-end)
into ~10-15 chunked calls (~15-30 seconds).

Packing uses two opaque ASCII markers Mayura passes through unchanged
(same technique as idiom placeholders in app/translate/idioms.py):

  [[ROW_n]]   between rows in a chunk. `n` is a monotonic sequence so
              the caller can rebuild ordering even if Mayura ever
              rearranges output (it usually doesn't).
  [[FLD]]     between the three fields within one row.

If a single row exceeds the input cap on its own, we fall back to
per-field translation for that row only.

Idiom pipeline
--------------
Every chunk goes through the idiom substitute/restore sandwich before
and after the Mayura call. `[[IDM_n]]` and `[[ROW_n]]`/[[FLD]] live in
distinct namespaces so they never collide.

Mode
----
`mode` selects Mayura's tone/register — formal / modern-colloquial /
classic-colloquial / code-mixed. See PRD §7.2 and the worker-facing
selector on ContractReaderPage.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

import httpx

from app.config import settings
from app.translate import idioms as idiom_mod


logger = logging.getLogger(__name__)


# BCP-47 short code → Sarvam's xx-IN format.
_LANG_MAP: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "bn": "bn-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "mr": "mr-IN",
}


# Sarvam Mayura input cap. Documented at 1000; we stay under 800 to
# leave headroom for idiom placeholders (each swap can expand slightly)
# and chunk markers.
_MAX_INPUT_CHARS = 800

# Boundary tokens. ASCII-bracketed, no natural-language content — same
# pattern as idiom placeholders. Mayura passes them through opaquely.
_ROW_MARKER_TEMPLATE = "[[ROW_{n}]]"
_ROW_MARKER_RE = re.compile(r"\[\[ROW_(\d+)\]\]")
_FIELD_SEP = "[[FLD]]"

# Text glue around markers so Mayura is more likely to preserve the
# neighbouring whitespace + treat markers as their own line-level
# tokens rather than run them into surrounding words.
_ROW_JOIN = "\n\n{marker}\n"
_FIELD_JOIN = f"\n{_FIELD_SEP}\n"


_client = httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))


class TranslationError(RuntimeError):
    """Raised when translation fails hard (missing API key, 4xx from
    Sarvam, empty response). Callers catch and degrade to the English
    source rather than fail the whole pipeline."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_supported(language: str) -> bool:
    return language.lower() in _LANG_MAP


@dataclass(frozen=True)
class _RowPayload:
    """One row's three fields, canonicalised for chunk packing."""
    clause_id: Any
    explanation: str
    implication: str
    action: str        # empty string when the source was None
    action_was_none: bool


def translate_stage_3(
    rendered_en: list[dict[str, Any]],
    *,
    target_language: str,
    mode: str = "formal",
) -> list[dict[str, Any]]:
    """Translate the English Stage 3 rendered array into target_language.

    Chunks rows into Mayura-cap-friendly batches by default. Long
    single rows fall back to per-field translation for that row only.
    Individual chunk failures degrade the affected rows to their
    English source rather than aborting the whole batch.
    """
    if target_language == "en":
        return list(rendered_en)  # no-op, defensive
    if not is_supported(target_language):
        raise TranslationError(
            f"unsupported target language {target_language!r}"
        )
    if not settings.sarvam_api_key:
        raise TranslationError(
            "SARVAM_API_KEY not configured — cannot translate output"
        )

    # Canonicalise all rows once so chunking + splitting operate on
    # a uniform shape (in particular: None action → "" for encoding,
    # remembered separately so the response preserves JSON null).
    payloads = [_canonicalise(row) for row in rendered_en]
    if not payloads:
        return []

    # Build a per-clause_id -> translated dict as chunks land, so a
    # failed chunk doesn't take down the rest.
    translated_by_id: dict[Any, dict[str, Any]] = {}

    for chunk in _pack_chunks(payloads, max_chars=_MAX_INPUT_CHARS):
        if len(chunk) == 1 and _encoded_length([chunk[0]]) > _MAX_INPUT_CHARS:
            # This one row can't fit even by itself — degrade to
            # per-field translation for it.
            try:
                translated_by_id[chunk[0].clause_id] = _translate_row_per_field(
                    chunk[0], target_language=target_language, mode=mode,
                )
            except Exception:
                logger.exception(
                    "translate: oversize row %s failed; keeping English",
                    chunk[0].clause_id,
                )
                translated_by_id[chunk[0].clause_id] = _english_fallback(chunk[0])
            continue

        try:
            for row_id, translated in _translate_chunk(
                chunk, target_language=target_language, mode=mode,
            ).items():
                translated_by_id[row_id] = translated
        except Exception:
            logger.exception(
                "translate: chunk of %d rows failed; falling back per-row",
                len(chunk),
            )
            for payload in chunk:
                try:
                    translated_by_id[payload.clause_id] = _translate_row_per_field(
                        payload, target_language=target_language, mode=mode,
                    )
                except Exception:
                    logger.exception(
                        "translate: per-row fallback for %s also failed; "
                        "keeping English",
                        payload.clause_id,
                    )
                    translated_by_id[payload.clause_id] = _english_fallback(payload)

    # Preserve original ordering — build the output in the same order
    # the caller sent rows.
    return [translated_by_id.get(p.clause_id, _english_fallback(p)) for p in payloads]


# ---------------------------------------------------------------------------
# Row canonicalisation
# ---------------------------------------------------------------------------


def _canonicalise(row: dict[str, Any]) -> _RowPayload:
    action_raw = row.get("action")
    action_str = (
        str(action_raw).strip() if action_raw is not None else ""
    )
    return _RowPayload(
        clause_id=row.get("clause_id"),
        explanation=str(row.get("explanation") or "").strip(),
        implication=str(row.get("implication") or "").strip(),
        action=action_str,
        action_was_none=action_raw is None,
    )


def _english_fallback(payload: _RowPayload) -> dict[str, Any]:
    """Return the row unchanged (English source) when translation fails.
    Frontend viewer falls back to Stage 3's English rendered array when
    translation.rendered is missing per-row, but we surface the same
    shape here for consistency."""
    return {
        "clause_id": payload.clause_id,
        "explanation": payload.explanation,
        "implication": payload.implication,
        "action": None if payload.action_was_none else (payload.action or None),
    }


# ---------------------------------------------------------------------------
# Chunk packing
# ---------------------------------------------------------------------------


def _encode_row_body(payload: _RowPayload) -> str:
    """The three-field body of a row, joined by [[FLD]] but WITHOUT the
    outer row marker. Used by both size estimation and chunk assembly."""
    return _FIELD_JOIN.join([
        payload.explanation,
        payload.implication,
        payload.action,
    ])


def _encoded_length(payloads: list[_RowPayload]) -> int:
    """Approximate serialised length of a chunk. Uses the largest ROW
    marker index the chunk would need (marker string grows with n)."""
    if not payloads:
        return 0
    marker_len = len(_ROW_MARKER_TEMPLATE.format(n=len(payloads)))
    row_overhead = marker_len + 3  # marker + surrounding \n\n...\n glue
    return sum(len(_encode_row_body(p)) for p in payloads) + row_overhead * len(payloads)


def _pack_chunks(
    payloads: list[_RowPayload], *, max_chars: int,
) -> Iterator[list[_RowPayload]]:
    """Greedy packer. Yields lists of payloads such that each list's
    encoded length stays under `max_chars`. A single row exceeding the
    cap is yielded as a one-element list so the caller can trigger the
    per-field fallback for it."""
    current: list[_RowPayload] = []
    for payload in payloads:
        candidate = current + [payload]
        if current and _encoded_length(candidate) > max_chars:
            yield current
            current = [payload]
        else:
            current = candidate
    if current:
        yield current


# ---------------------------------------------------------------------------
# Chunk translate (the hot path)
# ---------------------------------------------------------------------------


def _translate_chunk(
    payloads: list[_RowPayload],
    *,
    target_language: str,
    mode: str,
) -> dict[Any, dict[str, Any]]:
    """Encode the chunk into one string, translate, split back into
    per-row dicts keyed by clause_id.

    Raises on hard Mayura failure; caller falls back per-row."""
    encoded, row_order = _encode_chunk(payloads)

    # Idiom substitution wraps the full chunk. IDM placeholders and ROW
    # markers live in separate namespaces so no collision.
    subbed, subs = idiom_mod.substitute(encoded, target_language)
    translated_raw = _mayura(subbed, target_language=target_language, mode=mode)
    translated_raw = idiom_mod.restore(translated_raw, subs)

    parsed = _decode_chunk(translated_raw, row_order)
    if parsed is None:
        # Row markers got mangled — caller's chunk-level exception
        # handler falls back per-row.
        raise TranslationError(
            f"chunk decode failed: {len(payloads)} rows expected, "
            f"markers not recoverable"
        )

    out: dict[Any, dict[str, Any]] = {}
    for payload in payloads:
        fields = parsed.get(payload.clause_id)
        if fields is None:
            # Missing this row's markers in the response — degrade to
            # English for just this row.
            logger.info(
                "translate: row %s missing from chunk response; keeping English",
                payload.clause_id,
            )
            out[payload.clause_id] = _english_fallback(payload)
            continue
        explanation_t, implication_t, action_t = fields
        out[payload.clause_id] = {
            "clause_id": payload.clause_id,
            "explanation": explanation_t.strip(),
            "implication": implication_t.strip(),
            "action": None if payload.action_was_none else (action_t.strip() or None),
        }
    return out


def _encode_chunk(
    payloads: list[_RowPayload],
) -> tuple[str, list[tuple[int, Any]]]:
    """Serialise a chunk. Returns (payload_string, row_order) where
    row_order is a list of (marker_index, clause_id) so the decoder
    can re-associate markers to original rows."""
    parts: list[str] = []
    order: list[tuple[int, Any]] = []
    for i, payload in enumerate(payloads, start=1):
        marker = _ROW_MARKER_TEMPLATE.format(n=i)
        parts.append(_ROW_JOIN.format(marker=marker))
        parts.append(_encode_row_body(payload))
        order.append((i, payload.clause_id))
    return ("".join(parts).lstrip("\n"), order)


def _decode_chunk(
    translated: str,
    row_order: list[tuple[int, Any]],
) -> dict[Any, tuple[str, str, str]] | None:
    """Split the translated string on ROW markers, then split each row
    on FIELD separator. Returns {clause_id: (explanation, implication,
    action)} or None if the marker structure didn't survive."""
    id_by_marker = {n: cid for n, cid in row_order}

    # re.split with a capturing group gives us alternating (chunk,
    # marker_number, chunk, marker_number, ...). First element is
    # whatever was before ROW_1 (usually empty / whitespace).
    pieces = _ROW_MARKER_RE.split(translated)
    if len(pieces) < 3:
        return None
    # pieces = [leading, marker_1, body_1, marker_2, body_2, ...]
    out: dict[Any, tuple[str, str, str]] = {}
    idx = 1
    while idx < len(pieces) - 1:
        try:
            marker_num = int(pieces[idx])
        except ValueError:
            idx += 2
            continue
        body = pieces[idx + 1]
        cid = id_by_marker.get(marker_num)
        if cid is None:
            idx += 2
            continue
        # Split into three fields.
        fields = body.split(_FIELD_SEP)
        if len(fields) < 3:
            # Missing field markers within this row — skip; caller's
            # per-row fallback will handle it.
            idx += 2
            continue
        # If Mayura duplicated a FLD marker, we still want the FIRST
        # three chunks (explanation, implication, action).
        out[cid] = (fields[0], fields[1], _FIELD_SEP.join(fields[2:]))
        idx += 2

    # Did we actually recover most of the rows? A partial recovery
    # (< 50%) suggests marker collapse rather than genuine per-row
    # dropouts — bail so the caller falls back per-row cleanly.
    if len(out) < max(1, len(row_order) // 2):
        return None
    return out


# ---------------------------------------------------------------------------
# Per-row / per-field fallback (kept for oversize rows + chunk failures)
# ---------------------------------------------------------------------------


def _translate_row_per_field(
    payload: _RowPayload,
    *,
    target_language: str,
    mode: str,
) -> dict[str, Any]:
    """Translate one row by making up to three separate Mayura calls
    (one per non-empty field). Used when a chunk fails to decode, or
    when a single row exceeds the input cap on its own."""
    exp_t = (
        _translate_single(payload.explanation, target_language, mode=mode)
        if payload.explanation else ""
    )
    imp_t = (
        _translate_single(payload.implication, target_language, mode=mode)
        if payload.implication else ""
    )
    act_t = (
        _translate_single(payload.action, target_language, mode=mode)
        if payload.action else ""
    )
    return {
        "clause_id": payload.clause_id,
        "explanation": exp_t,
        "implication": imp_t,
        "action": None if payload.action_was_none else (act_t or None),
    }


def _translate_single(
    text: str,
    target_language: str,
    *,
    mode: str = "formal",
    apply_idioms: bool = True,
) -> str:
    """Single Mayura call for a raw string. Applies idiom sub/restore
    unless disabled (chunk path handles idioms around the whole
    chunk, so calls from there pass apply_idioms=False)."""
    if not text.strip():
        return ""

    if apply_idioms:
        subbed, subs = idiom_mod.substitute(text, target_language)
    else:
        subbed, subs = text, []

    translated = _mayura(subbed, target_language=target_language, mode=mode)
    if subs:
        translated = idiom_mod.restore(translated, subs)
    return translated


# ---------------------------------------------------------------------------
# Low-level HTTP
# ---------------------------------------------------------------------------


def _mayura(
    text: str, *, target_language: str, mode: str,
) -> str:
    """Bare Mayura POST with the jittered 429/5xx retry policy. No
    idiom handling — the caller wraps this."""
    body = {
        "input": text,
        "source_language_code": "en-IN",
        "target_language_code": _LANG_MAP[target_language],
        "mode": mode,
        "model": "mayura:v1",
        "enable_preprocessing": False,
    }
    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "Content-Type": "application/json",
    }
    url = "https://api.sarvam.ai/translate"

    max_attempts = 3
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = _client.post(url, json=body, headers=headers)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                delay = min(8.0, (2 ** attempt) + random.uniform(0, 0.5))
                logger.warning(
                    "mayura %s on attempt %d/%d; sleeping %.1fs",
                    resp.status_code, attempt, max_attempts, delay,
                )
                time.sleep(delay)
                continue
            if resp.status_code >= 400:
                raise TranslationError(
                    f"mayura {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            translated = data.get("translated_text")
            if not isinstance(translated, str):
                raise TranslationError(
                    f"mayura returned unexpected shape: {str(data)[:200]}"
                )
            return translated
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            delay = min(8.0, (2 ** attempt) + random.uniform(0, 0.5))
            logger.warning(
                "mayura transport error on attempt %d/%d (%s); sleeping %.1fs",
                attempt, max_attempts, type(exc).__name__, delay,
            )
            time.sleep(delay)
    if last_exc:
        raise TranslationError(f"mayura: retries exhausted ({last_exc})") from last_exc
    raise TranslationError("mayura: retries exhausted")
