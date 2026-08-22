"""Stage 2 — Research.

Takes the structured clauses from Stage 1 and annotates each with:
  - risk: red (adverse to the worker), amber (worth knowing), green (favourable)
  - statute: the Indian law reference that governs this clause, if any
  - note: a short (1-2 sentence) explanation of why the clause got its risk tier

Stays in English — the reasoning about Indian labour law is easier to
control in one canonical language, and Stage 3 handles the translation
to the worker's UI language separately. Kept generative (LLM) rather
than rule-based because clause language varies enormously; a rules
engine would need thousands of patterns to cover the corpus.

Idempotent: re-running on the same Stage 1 output produces the same
schema, though the annotation text will vary slightly across runs.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.l2_agents.llm_provider import get_provider


logger = logging.getLogger(__name__)


_ALLOWED_RISK = {"red", "amber", "green"}


_SYSTEM = """You are analysing a gig-worker contract clause by clause against Indian labour law.

Framework you know:
- Code on Social Security 2020 (Sections 113-114 recognise platform-based
  gig workers as a distinct category, mandate a Social Security Fund).
- Karnataka Platform-Based Gig Workers (Social Security and Welfare)
  Ordinance 2025 (state welfare board + 1-2% cess).
- Rajasthan Platform-Based Gig Workers (Registration and Welfare) Act 2023.
- Motor Vehicles Rules amendment 2024 (aggregator responsibility for driver welfare).
- POSH Act 2013 (workplace harassment).
- Fairwork India Annual Report — five principles: fair pay, fair conditions,
  fair contracts, fair management, fair representation.
- Industrial Disputes Act 1947 Section 2A (individual dispute recourse).
- Consumer Protection Act 2019 (alternate route for wage disputes).

Risk tiers:
- red    Clause is adverse to the worker: unilateral deactivation without
         notice, opaque per-order pricing changes, broad indemnification
         of the platform, waiver of statutory rights, non-compete, one-way
         arbitration in another jurisdiction.
- amber  Clause is worth knowing but not necessarily unfair: exclusivity,
         data-sharing consent, dispute-resolution requirements, background
         verification, vehicle-condition requirements.
- green  Clause is favourable or protective: insurance cover, defined
         payment schedules, injury compensation, grievance channels,
         explicit rest-hour limits.

Return ONLY a JSON object with this shape (no prose):

{
  "annotations": [
    {
      "clause_id": "<matches an id from the input clauses>",
      "risk": "red" | "amber" | "green",
      "statute": "<statute or scheme name, or null if none applies>",
      "note": "<one to two sentence English explanation of the risk assessment>"
    },
    ...
  ]
}

Every input clause must have a corresponding annotation — do not skip clauses.
If a clause is boilerplate (definitions, signatures, notices) mark it green
with statute=null and a brief note.
"""


def annotate(stage_1_output: dict[str, Any]) -> dict[str, Any]:
    """Run Stage 2. `stage_1_output` is the dict Stage 1 produced.
    Reasoning is always in English regardless of contract language."""
    clauses = stage_1_output.get("clauses") or []
    if not clauses:
        return {"annotations": [], "error": None}

    contract_type = stage_1_output.get("contract_type") or "unknown"

    payload = {
        "contract_type": contract_type,
        "clauses": [
            {
                "id": c["id"],
                "heading": c.get("heading"),
                "section_number": c.get("section_number"),
                "text": c["text"],
            }
            for c in clauses
        ],
    }

    provider = get_provider("en")  # Stage 2 always reasons in English
    raw = provider.chat(
        role="smart",
        system=_SYSTEM,
        user=(
            "Analyse each clause and return the annotations JSON. "
            "Contract:\n" + json.dumps(payload, indent=2)
        ),
        # Match Stage 1's budget — a contract with 20+ clauses produces
        # 20 annotation objects, each with a paragraph note.
        max_tokens=32768,
        temperature=0.1,
    )
    return _parse(raw, expected_ids={c["id"] for c in clauses})


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _parse(raw: str, *, expected_ids: set[str]) -> dict[str, Any]:
    if not raw or not raw.strip():
        return _empty_result("empty response from stage 2 llm", expected_ids)

    text = raw.strip()
    m = _CODE_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("stage 2: could not parse response; raw=%r", text[:300])
        return _empty_result("could not parse stage 2 response as JSON", expected_ids)

    if not isinstance(data, dict):
        return _empty_result("stage 2 response was not an object", expected_ids)

    annotations_raw = data.get("annotations") or []
    annotations = _clean_annotations(annotations_raw)

    # Backfill any missing clauses so the downstream viewer always has
    # something to show. Missing annotations default to amber ("worth
    # knowing") with a fallback note — deliberately not green because
    # a missing annotation is the model failing to reason, not evidence
    # of harmlessness.
    seen = {a["clause_id"] for a in annotations}
    for cid in expected_ids - seen:
        annotations.append({
            "clause_id": cid,
            "risk": "amber",
            "statute": None,
            "note": "This clause was not annotated by the analyser. Review it manually.",
        })

    return {"annotations": annotations, "error": None}


def _clean_annotations(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = row.get("clause_id")
        if not isinstance(cid, str) or not cid.strip():
            continue
        risk = str(row.get("risk") or "amber").lower()
        if risk not in _ALLOWED_RISK:
            risk = "amber"
        statute = row.get("statute")
        statute = str(statute).strip() if isinstance(statute, str) and statute.strip() else None
        note = str(row.get("note") or "").strip() or "No annotation provided."
        out.append({
            "clause_id": cid,
            "risk": risk,
            "statute": statute,
            "note": note,
        })
    return out


def _empty_result(error: str, expected_ids: set[str]) -> dict[str, Any]:
    return {
        "annotations": [
            {
                "clause_id": cid,
                "risk": "amber",
                "statute": None,
                "note": "Stage 2 analysis failed. Please retry.",
            }
            for cid in expected_ids
        ],
        "error": error,
    }
