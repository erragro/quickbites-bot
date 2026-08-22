"""
Stage 3 Respond — given the VALIDATED action set, write a warm, short customer
reply and emit the final simulator-schema actions list. Never reveals bot
identity or policy text. Uses Sonnet for tone quality.

Returns:
  bot_message: str
  actions: list[dict]   (shape matches simulator SIMULATOR_API.md)
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from app.l2_agents.language_detector import LANGUAGE_NAMES
from app.l2_agents.llm_provider import get_provider
from app.schemas import (
    Classification,
    EnrichedContext,
    ProposedAction,
    Stage3Output,
)


_SYSTEM_BASE = """You write short, warm, human-sounding replies for a food-delivery support agent.

Constraints:
- Do NOT reveal you are a bot or an AI. Do NOT mention "policy", "system", "rules",
  "our guidelines", or internal scoring.
- Do NOT tell the customer what actions you've taken in machine/jargon terms.
  Speak like a human support agent: "I've credited ₹200 to your wallet for the missing item."
- Keep the reply to 1–3 short sentences.
- If an escalation action is present, reassure the customer that a colleague will review —
  but only ONCE per conversation. If the context shows an escalation already happened in a
  prior turn, do NOT repeat "a colleague will reach out" again.
- If a close action is present, confirm the resolution briefly and end politely. If the
  context shows `already_escalated` and this turn is closing, thank the customer for their
  patience and confirm the handoff rather than re-announcing it.
- CLOSE HARD RULE: when `close` is in validated_actions, your reply is a terminal closing —
  do NOT ask ANY follow-up questions, do NOT invite the customer to share more details,
  do NOT say "let me know if..." or "feel free to reach out". Wish them well and stop.
  A message that asks for information while the session closes is the worst failure mode
  on this channel.
- If no money is being issued, do NOT volunteer money.
- If verbal abuse or threats were detected, stay calm and professional. Do not match energy.

WHEN `validated_actions` IS EMPTY:
  - If `order_summary` is null AND the customer raised a concrete complaint (missing
    item, cold food, wrong order, never arrived, rider issue, promo failed, double
    charge), acknowledge empathetically and ask for ONE specific piece of information
    to help: usually the order number, sometimes the item or the approximate delivery
    time. Example: "I'm really sorry to hear that. Could you share the order number
    so I can look into it right now?" — this is the single most important move, keep
    it front-and-centre.
  - If the customer asked to cancel, point them to the cancel option in the app;
    don't pretend you can cancel from this chat.
  - Otherwise give a warm one-liner that keeps the door open.

DO NOT repeat the prior bot message. You will be shown `prior_bot_message` in the context;
your reply MUST use different phrasing and reference specific details from the current
customer message (the order number they mentioned, the item, the amount). Saying the same
thing twice in a row is the worst thing you can do on this channel.

Return ONLY a JSON object, no prose:
{
  "bot_message": "<the reply>"
}
"""


def _system_prompt(language: str) -> str:
    name = LANGUAGE_NAMES.get(language, "English")
    return (
        _SYSTEM_BASE
        + f"\n\nRespond in {name}, matching the language the customer wrote in. "
        "Do not switch to English unless the customer does."
    )


_ACTION_SUMMARY_KEYS = {
    "issue_refund": ("order_id", "amount_inr", "method"),
    "file_complaint": ("order_id", "target_type"),
    "escalate_to_human": ("reason",),
    "flag_abuse": ("reason",),
    "close": ("outcome_summary",),
}


def _summarise_actions(actions: list[ProposedAction]) -> list[dict[str, Any]]:
    out = []
    for a in actions:
        d = a.model_dump(exclude_none=True)
        out.append(d)
    return out


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _parse_message(raw: str) -> str:
    if not raw:
        return "Thanks for reaching out — a team member will follow up."
    fenced = _CODE_FENCE_RE.search(raw)
    candidate = fenced.group(1).strip() if fenced else None
    if candidate is None:
        m = _JSON_OBJ_RE.search(raw)
        candidate = m.group(0) if m else None
    if not candidate:
        return raw.strip()[:500] or "Thanks for reaching out."
    try:
        data = json.loads(candidate)
        msg = data.get("bot_message") or data.get("message") or ""
        return msg.strip() or "Thanks for reaching out."
    except json.JSONDecodeError:
        last = candidate.rfind("}")
        if last > 0:
            try:
                data = json.loads(candidate[: last + 1])
                return (data.get("bot_message") or data.get("message") or "").strip() or "Thanks for reaching out."
            except json.JSONDecodeError:
                pass
        return raw.strip()[:500] or "Thanks for reaching out."


def _to_simulator_action(a: ProposedAction) -> dict[str, Any] | None:
    """Shape actions to match docs/SIMULATOR_API.md exactly."""
    if a.type == "issue_refund":
        if not (a.order_id and a.amount_inr and a.method):
            return None
        return {
            "type": "issue_refund",
            "order_id": a.order_id,
            "amount_inr": a.amount_inr,
            "method": a.method,
        }
    if a.type == "file_complaint":
        if not (a.order_id and a.target_type):
            return None
        return {
            "type": "file_complaint",
            "order_id": a.order_id,
            "target_type": a.target_type,
        }
    if a.type == "escalate_to_human":
        return {"type": "escalate_to_human", "reason": a.reason or "Needs human review."}
    if a.type == "flag_abuse":
        return {"type": "flag_abuse", "reason": a.reason or "Abuse pattern detected."}
    if a.type == "close":
        return {"type": "close", "outcome_summary": a.outcome_summary or "Issue resolved."}
    return None


def respond(
    *,
    customer_message: str,
    history_snippet: str,
    classification: Classification,
    ctx: EnrichedContext,
    final_actions: list[ProposedAction],
    prior_bot_message: str | None = None,
    already_escalated: bool = False,
    language: str = "en",
) -> Stage3Output:
    payload = {
        "customer_message": customer_message,
        "prior_bot_message": prior_bot_message,
        "already_escalated": already_escalated,
        "history": history_snippet,
        "classification": classification.model_dump(),
        "validated_actions": _summarise_actions(final_actions),
        "order_summary": (
            {
                "id": ctx.order.id,
                "restaurant": ctx.restaurant.name if ctx.restaurant else None,
                "total_inr": ctx.order.total_inr,
                "status": ctx.order.status,
            }
            if ctx.order
            else None
        ),
        "customer_first_name": (
            ctx.customer.name.split()[0] if ctx.customer and ctx.customer.name else None
        ),
    }

    raw = get_provider(language).chat(
        role="smart",
        system=_system_prompt(language),
        user=(
            "Write the reply given the decisions already made. "
            "Context:\n" + json.dumps(payload, default=str, indent=2)
        ),
        max_tokens=1200,
        temperature=0.4,
    )
    bot_message = _parse_message(raw)

    simulator_actions = [
        shaped for a in final_actions
        if (shaped := _to_simulator_action(a)) is not None
    ]

    return Stage3Output(bot_message=bot_message, actions=simulator_actions)


# ---------------------------------------------------------------------------
# Streaming variant
#
# Used by the SSE chat endpoint. Yields raw text chunks as the model
# produces them; the final actions list is known ahead of time (Stage 2
# already computed it) and the caller emits it in the SSE 'done' event.
#
# Uses a plain-text prompt instead of the JSON-wrapped one — asking a
# streaming model to emit `{"bot_message":"..."}` chunk-by-chunk means
# the frontend would see quote characters and brace scaffolding mid-
# stream. Cleaner to just stream the prose directly.
# ---------------------------------------------------------------------------


_STREAM_SYSTEM_SUFFIX = (
    "\n\n"
    "IMPORTANT: reply ONLY with the customer-facing text of your response. "
    "No JSON, no code fences, no quotes wrapping the whole response. "
    "Just the message itself."
)


def respond_stream(
    *,
    customer_message: str,
    history_snippet: str,
    classification: Classification,
    ctx: EnrichedContext,
    final_actions: list[ProposedAction],
    prior_bot_message: str | None = None,
    already_escalated: bool = False,
    language: str = "en",
) -> Iterator[str]:
    payload = {
        "customer_message": customer_message,
        "prior_bot_message": prior_bot_message,
        "already_escalated": already_escalated,
        "history": history_snippet,
        "classification": classification.model_dump(),
        "validated_actions": _summarise_actions(final_actions),
        "order_summary": (
            {
                "id": ctx.order.id,
                "restaurant": ctx.restaurant.name if ctx.restaurant else None,
                "total_inr": ctx.order.total_inr,
                "status": ctx.order.status,
            }
            if ctx.order
            else None
        ),
        "customer_first_name": (
            ctx.customer.name.split()[0] if ctx.customer and ctx.customer.name else None
        ),
    }

    yield from get_provider(language).chat_stream(
        role="smart",
        system=_system_prompt(language) + _STREAM_SYSTEM_SUFFIX,
        user=(
            "Write the reply given the decisions already made. "
            "Context:\n" + json.dumps(payload, default=str, indent=2)
        ),
        max_tokens=1200,
        temperature=0.4,
    )


def stream_actions(final_actions: list[ProposedAction]) -> list[dict[str, Any]]:
    """Shape actions for the simulator schema — same rule as respond()'s
    trailing list comprehension. Extracted so the SSE endpoint can emit
    it in the 'done' event without going through respond()."""
    return [
        shaped for a in final_actions
        if (shaped := _to_simulator_action(a)) is not None
    ]
