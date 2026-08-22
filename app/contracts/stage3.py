"""Stage 3 — Synthesise (English only).

Merges Stage 1 (clauses) + Stage 2 (annotations) into the worker-facing
rendition. For each clause, produces three pieces of English text:
  - explanation  Plain-language rewrite of the clause.
  - implication  What this clause means for the worker in practice.
  - action       Concrete step to take, or null if nothing.

Output is always English. Translation to the worker's target language
happens in a separate pass via Sarvam Mayura (see translate.py) —
Gemini is smartest + fastest reasoning in English, Mayura is the
purpose-built Indic translator. Two providers, two responsibilities.

The viewer joins this Stage 3 output back against Stage 1 (for the
original clause text, kept verbatim in whatever language the contract
was written in) and Stage 2 (for the risk colour + statute) at render
time. When contract.target_language != 'en', the viewer picks the
translated version stored under stages.stage_3.translation.rendered
instead of this raw English rendered array.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.l2_agents.llm_provider import get_provider


logger = logging.getLogger(__name__)


_SYSTEM = """You are producing a worker-friendly rendition of a contract clause in English.

For EACH clause you're given, produce three short pieces of English text:

- explanation  Plain-language rewrite of the clause. 1-2 sentences. Not a
               summary — a rewrite the worker can understand. Do NOT lose
               material meaning. Do NOT introduce new obligations.
- implication  What this clause means for the worker in practice.
               1 sentence. Focus on the worker's rights or exposure.
- action       If the worker should do something about this clause, one
               concrete step in 1 sentence. If nothing needs doing,
               return null (JSON null, not the string "null").

Tone rules (strict — Mayura will translate this English text into the
worker's language, so tone preserved here carries through):
- Warm, direct, informational. Register of a helpful older sibling.
- No em dashes (—). Use commas or full stops.
- No corporate register ("kindly", "we regret", "as per").
- No policy language ("as per our terms", "per our guidelines").
- No negative-emotion vocabulary ("frustration", "disappointment", "annoying").
- Max 3 sentences per field.
- Use simple English words. Assume a translator will render each field
  into another language; avoid idioms and puns.

The 'risk' field per clause tells you whether this clause is adverse
(red), worth-knowing (amber), or favourable (green) — use that to
calibrate the action field: red clauses often warrant an action, green
clauses usually don't.

Return ONLY a JSON object with this shape (no prose, no code fences):

{
  "rendered": [
    {
      "clause_id": "<matches an id from the input>",
      "explanation": "<plain-language English rewrite>",
      "implication": "<what this means for the worker, in English>",
      "action": "<one concrete step in English, or null>"
    },
    ...
  ]
}
"""


def synthesise(
    stage_1_output: dict[str, Any],
    stage_2_output: dict[str, Any],
) -> dict[str, Any]:
    """Run Stage 3. Always emits English. Returns {rendered: [...], error: None}.
    Translation to the worker's chosen target language happens in a
    subsequent pass via translate.translate_stage_3()."""
    clauses = stage_1_output.get("clauses") or []
    if not clauses:
        return {"rendered": [], "error": None}

    annotations = {
        a["clause_id"]: a for a in (stage_2_output.get("annotations") or [])
        if isinstance(a, dict) and isinstance(a.get("clause_id"), str)
    }

    # Batch payload — one LLM call for all clauses.
    payload = {
        "clauses": [
            {
                "id": c["id"],
                "heading": c.get("heading"),
                "text": c["text"],
                "risk": annotations.get(c["id"], {}).get("risk", "amber"),
                "statute": annotations.get(c["id"], {}).get("statute"),
            }
            for c in clauses
        ],
    }

    provider = get_provider("en")  # Stage 3 always reasons in English
    raw = provider.chat(
        role="smart",
        system=_SYSTEM,
        user=(
            "Render each clause in English following the rules above. Clauses:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        ),
        # Match Stage 1/2 budget for long contracts. Each clause
        # renders to three short strings (explanation + implication +
        # action) so 20 clauses fit in ~10K tokens; the ceiling is
        # headroom for outlier long contracts.
        max_tokens=32768,
        temperature=0.2,
    )
    return _parse(raw, expected_ids={c["id"] for c in clauses})


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _parse(raw: str, *, expected_ids: set[str]) -> dict[str, Any]:
    if not raw or not raw.strip():
        return _empty_result("empty response from stage 3 llm", expected_ids)

    text = raw.strip()
    m = _CODE_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("stage 3: could not parse response; raw=%r", text[:300])
        return _empty_result("could not parse stage 3 response as JSON", expected_ids)

    if not isinstance(data, dict):
        return _empty_result("stage 3 response was not an object", expected_ids)

    rendered = _clean_rendered(data.get("rendered") or [])

    # Backfill missing clauses so the viewer always has something to show.
    seen = {r["clause_id"] for r in rendered}
    for cid in expected_ids - seen:
        rendered.append({
            "clause_id": cid,
            "explanation": "This clause could not be re-rendered.",
            "implication": "Review the original text.",
            "action": None,
        })

    return {"rendered": rendered, "error": None}


def _clean_rendered(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = row.get("clause_id")
        if not isinstance(cid, str) or not cid.strip():
            continue
        explanation = _clean_field(row.get("explanation"), fallback="")
        implication = _clean_field(row.get("implication"), fallback="")
        action_raw = row.get("action")
        # Explicit null OR empty string → no action. Also catch the
        # literal strings "null" / "none" / "n/a" because Gemini
        # sometimes returns those despite the instruction; rendering
        # them verbatim would put "Suggested action: null" in the UI.
        if action_raw is None:
            action = None
        else:
            action_str = _clean_field(action_raw, fallback="")
            if action_str.lower() in {"null", "none", "n/a", "na", "-"}:
                action = None
            else:
                action = action_str or None
        out.append({
            "clause_id": cid,
            "explanation": explanation,
            "implication": implication,
            "action": action,
        })
    return out


def _clean_field(value: Any, *, fallback: str) -> str:
    """Strip em dashes as a defence in depth against the LLM slipping
    them into user-facing copy. Tone spec section 8.4 bans them."""
    if not isinstance(value, str):
        return fallback
    return value.strip().replace("—", ",")


def _empty_result(error: str, expected_ids: set[str]) -> dict[str, Any]:
    return {
        "rendered": [
            {
                "clause_id": cid,
                "explanation": "Rendering failed. Please retry.",
                "implication": "",
                "action": None,
            }
            for cid in expected_ids
        ],
        "error": error,
    }
