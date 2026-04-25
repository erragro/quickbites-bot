"""
Phase 1 Validator — the bouncer. Cheap, deterministic, no LLM.
Detects malformed input and prompt-injection attempts. Does NOT short-circuit
the pipeline on injection (we still need to reply politely); instead it flags
the context so Stage 2 can strip any action the model slipped in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?previous\s+instructions",
    r"disregard\s+(all\s+|any\s+)?previous",
    r"you\s+are\s+now\s+",
    r"system\s*prompt",
    r"jailbreak",
    r"act\s+as\s+(if|a)\s+",
    r"pretend\s+(to\s+be|you\s+are)",
    r"developer\s+mode",
    r"forget\s+(everything|all|your\s+instructions)",
    r"bypass\s+(the\s+)?(policy|rules|restrictions)",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

ABUSE_PATTERNS = [
    r"\b(fuck|fucking|fck|shit|bitch|bastard|bloody\s+hell|motherf)\w*",
    r"chargeback",
    r"sue\s+you",
    r"lawsuit",
]
_ABUSE_RE = re.compile("|".join(ABUSE_PATTERNS), re.IGNORECASE)


@dataclass
class ValidatorResult:
    passed: bool
    message: str
    injection_attempt: bool = False
    verbal_abuse: bool = False
    failure_reason: str | None = None


def run(customer_message: str) -> ValidatorResult:
    text = (customer_message or "").strip()
    if not text:
        return ValidatorResult(
            passed=False,
            message=text,
            failure_reason="empty_message",
        )

    if len(text) > 5000:
        return ValidatorResult(
            passed=False,
            message=text[:5000],
            failure_reason="message_too_long",
        )

    return ValidatorResult(
        passed=True,
        message=text,
        injection_attempt=bool(_INJECTION_RE.search(text)),
        verbal_abuse=bool(_ABUSE_RE.search(text)),
    )
