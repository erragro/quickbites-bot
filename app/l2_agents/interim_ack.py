"""
Interim-acknowledgment picker for free-text chat turns.

Runs synchronously against the customer's message BEFORE Stage 0 (so it
adds ~1ms, not 1000ms). If the message obviously references an order
number or matches a matrix-actionable intent, we emit a short human-
shaped acknowledgment RIGHT AWAY on the SSE stream, then run the slow
pipeline behind it.

Not intended to be perfect — a miss just means we skip the ack and go
straight into streaming Stage 3. False positives on tone (saying
"looking into your order" for a "thanks!" turn) are more expensive than
false negatives, so the rules are conservative.

Chip-tap turns already get an ack from acknowledgment_templates; this
module is the free-text equivalent.
"""

from __future__ import annotations

import random
import re
from typing import Optional


# Order-id-like patterns customers use in Indian food-delivery chat.
_ORDER_ID_RE = re.compile(r"\b(?:order\s*(?:no\.?|number|#|is)?\s*[:# ]*)?#?(\d{2,7})\b", re.IGNORECASE)

# Cheap intent hints. Each maps to (matched?, entity-aware ack pool).
_INTENT_HINTS: list[tuple[re.Pattern[str], list[str]]] = [
    # Missing item
    (
        re.compile(r"\b(missing|didn'?t (get|receive)|not delivered|short|incomplete)\b", re.I),
        [
            "Sorry to hear that — pulling up the order to see what's missing.",
            "Ugh, that's frustrating. Give me a moment to check what wasn't delivered.",
        ],
    ),
    # Cold food
    (
        re.compile(r"\b(cold|not (hot|warm)|stale|congealed)\b", re.I),
        [
            "Cold food is the worst — checking the order now.",
            "Sorry about that. Let me look at what happened.",
        ],
    ),
    # Wrong order
    (
        re.compile(r"\b(wrong|different|incorrect|not what|not mine)\b", re.I),
        [
            "That's not right — let me pull up the order and figure out what happened.",
            "Sorry for the mixup. Give me a sec to check.",
        ],
    ),
    # Never arrived
    (
        re.compile(r"\b(never (arrived|came|delivered)|didn'?t arrive|no delivery|not delivered)\b", re.I),
        [
            "That's really frustrating — checking the delivery record now.",
            "Let me look into what happened with the delivery.",
        ],
    ),
    # Late
    (
        re.compile(r"\b(late|delayed|taking (too )?long|slow)\b", re.I),
        [
            "Sorry about the wait — pulling up the delivery details.",
            "Let me check what's happening with the delivery.",
        ],
    ),
    # Rider issues
    (
        re.compile(r"\b(rider|delivery (person|guy|man|boy)|driver)\b", re.I),
        [
            "Let me look at the rider's details for the order.",
            "Checking the delivery info now.",
        ],
    ),
    # Payment / refund
    (
        re.compile(r"\b(refund|charged (twice|two times)|double charge|payment|money back)\b", re.I),
        [
            "Sorry to hear that — let me pull up the payment on the order.",
            "Give me a moment to look at the transaction.",
        ],
    ),
    # Promo
    (
        re.compile(r"\b(promo|discount|coupon|voucher|offer code)\b", re.I),
        [
            "Promo codes should just work — let me check what happened.",
            "Give me a sec to look at the promo on your order.",
        ],
    ),
]


# Generic order-only fallback when the message names an order but no
# intent verb matched. Still better than silence for free-text turns.
_ORDER_ONLY_ACK = [
    "Give me a moment to pull up order #{order_id}.",
    "Looking into order #{order_id} now.",
    "On it — checking order #{order_id}.",
]


def pick_interim_ack(message: str) -> Optional[str]:
    """
    Return a short interim-ack string for this customer message, or None
    if nothing matched cleanly. Called synchronously by the SSE endpoint
    before it kicks off the slow pipeline.
    """
    if not message or not message.strip():
        return None

    order_id_match = _ORDER_ID_RE.search(message)
    order_id = order_id_match.group(1) if order_id_match else None

    # Intent-shaped hits win — they say something specific about what
    # the customer told us. Order-only hits are the fallback.
    for pattern, pool in _INTENT_HINTS:
        if pattern.search(message):
            return random.choice(pool)

    if order_id:
        return random.choice(_ORDER_ONLY_ACK).format(order_id=order_id)

    return None
