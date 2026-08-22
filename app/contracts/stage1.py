"""Stage 1 — Understand.

Reads the OCR'd text of a contract and extracts a structured list of
clauses plus a contract-type classification. No legal reasoning happens
here (Stage 2 does that); this stage just imposes a schema on prose so
the downstream annotator has predictable shapes to work with.

The `clauses` array is what the viewer renders directly — each clause
becomes a row in the clause-by-clause UI, and its id is what the "ask
about this clause" chatbot hook references. Ids are stable strings so
they survive re-processing (rerunning Stage 1 on the same OCR text
produces the same ids).

Contract type is a fixed enum: aggregator | labour | vendor | rental |
unknown. Aggregator is the most common (Swiggy / Uber / Ola / Rapido);
labour covers direct-employment contracts; vendor covers B2B supply
agreements a gig-adjacent business might sign; rental covers vehicle
leases (common for delivery riders); unknown when the classifier can't
decide with confidence.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.l2_agents.llm_provider import get_provider


logger = logging.getLogger(__name__)


_ALLOWED_TYPES = {"aggregator", "labour", "vendor", "rental", "unknown"}


_SYSTEM = """You are analysing a contract or agreement between a worker and a company/platform.

Your job is to:

1. Extract each clause as a separate entry. A clause is a numbered section,
   a titled paragraph, or any standalone provision. Preserve the original
   language — do NOT translate the clause text.

2. Classify the contract as one of:
   - aggregator  (worker signs onto a platform: Swiggy, Uber, Ola, Rapido, Urban Company, etc.)
   - labour      (direct employment contract with a named employer)
   - vendor      (business-to-business supply agreement)
   - rental      (vehicle or equipment lease agreement)
   - unknown     (cannot determine with confidence)

Return ONLY a JSON object with this shape (no prose):

{
  "contract_type": "<one of the five above>",
  "confidence": <float 0.0 to 1.0>,
  "clauses": [
    {
      "id": "<stable string, e.g. clause_1 or clause_3a>",
      "heading": "<the clause heading or null if there isn't one>",
      "section_number": "<the section number as written, or null>",
      "text": "<the verbatim clause text in the original language>"
    },
    ...
  ]
}

Guidelines:
- If the document has explicit numbered clauses (1., 2.1, 3(a)), use those numbers in section_number and derive id from them.
- If there are no explicit numbers, invent stable ids: clause_1, clause_2, ...
- Preserve line breaks within a clause using \\n.
- If the OCR text is garbled or clearly not a contract, return contract_type='unknown', confidence=0, clauses=[].
- Do NOT summarise or reword clauses. Verbatim only.
"""


def analyse(ocr_text: str, language: str = "en") -> dict[str, Any]:
    """Run Stage 1 on the OCR text. Returns the parsed dict; the caller
    persists it into the row's `stages.stage_1` slot.

    Language routing: pass the detected language of the contract, not the
    UI language of the user. Gemini reads all 7 target languages; Sarvam
    handles the rest. But because clauses can be in mixed languages
    (English preamble + Hindi body) we pass the majority language.
    """
    provider = get_provider(language)

    raw = provider.chat(
        role="smart",
        system=_SYSTEM,
        user=f"OCR text of the contract:\n\n{ocr_text}",
        # Real gig-worker contracts run 3-8 pages of dense legalese, so
        # the structured-JSON output (verbatim clause text × N clauses)
        # regularly hits 20K+ tokens. Anything below and Gemini's output
        # truncates mid-clause, which explodes our JSON parser and
        # produces zero clauses. Gemini 2.5 Flash caps at 65K output.
        max_tokens=32768,
        temperature=0.0,
    )

    return _parse(raw)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _parse(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return _empty_result("empty response from stage 1 llm")

    text = raw.strip()
    # Strip code fences if Gemini added them despite the instruction.
    m = _CODE_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # Log both the head and the tail — a truncated response looks
        # fine at the head but breaks at the tail, and vice versa.
        logger.warning(
            "stage 1: could not parse response as JSON (%s); "
            "raw len=%d, head=%r, tail=%r",
            exc, len(text), text[:200], text[-200:],
        )
        # Salvage attempt: some responses truncate mid-clause. Look for
        # the last complete clause boundary and try to reconstruct.
        recovered = _try_recover_truncated(text)
        if recovered:
            logger.info("stage 1: recovered %d clauses from truncated response", len(recovered.get("clauses") or []))
            return _finalize(recovered)
        return _empty_result(
            f"could not parse Gemini's response as JSON. It may have run "
            f"past the output limit (response was {len(text)} characters)."
        )

    if not isinstance(data, dict):
        return _empty_result("stage 1 response was not an object")

    return _finalize(data)


def _finalize(data: dict) -> dict[str, Any]:
    contract_type = str(data.get("contract_type") or "unknown").lower()
    if contract_type not in _ALLOWED_TYPES:
        contract_type = "unknown"

    try:
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    clauses_raw = data.get("clauses") or []
    clauses = _clean_clauses(clauses_raw)

    return {
        "contract_type": contract_type,
        "confidence": confidence,
        "clauses": clauses,
        "error": None,
    }


def _try_recover_truncated(text: str) -> dict[str, Any] | None:
    """Salvage a truncated Stage 1 response. Gemini's structured output
    typically dies mid-clause when it runs out of tokens: opening braces
    are complete but the last clause is half-written and the closing
    array + object braces are missing. Walk backwards to the last
    complete '}' inside the clauses array, then reassemble.
    """
    # Locate the start of the clauses array.
    array_start = text.find('"clauses"')
    if array_start < 0:
        return None
    bracket_start = text.find("[", array_start)
    if bracket_start < 0:
        return None

    # Find the last complete top-level '}' inside the array by depth-tracking.
    depth = 0
    last_complete_end = -1
    i = bracket_start + 1
    in_string = False
    escaped = False
    while i < len(text):
        c = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    last_complete_end = i
        i += 1

    if last_complete_end < 0:
        return None

    # Reconstruct: everything up to the last complete '}', then close
    # the array + the outer object. contract_type + confidence come
    # from before the clauses array — parse the head separately.
    salvaged = text[:last_complete_end + 1] + "]}"
    try:
        return json.loads(salvaged)
    except json.JSONDecodeError:
        return None


def _clean_clauses(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        cid = str(row.get("id") or f"clause_{i}")
        heading = row.get("heading")
        heading = str(heading).strip() if isinstance(heading, str) and heading.strip() else None
        section_number = row.get("section_number")
        section_number = (
            str(section_number).strip()
            if isinstance(section_number, str) and section_number.strip()
            else None
        )
        out.append({
            "id": cid,
            "heading": heading,
            "section_number": section_number,
            "text": text.strip(),
        })
    return out


def _empty_result(error: str) -> dict[str, Any]:
    return {
        "contract_type": "unknown",
        "confidence": 0.0,
        "clauses": [],
        "error": error,
    }
