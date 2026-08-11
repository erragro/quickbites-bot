"""
Independent local evaluation harness — does NOT depend on the external
QuickBites simulator (whose 22-scenario prod quota is already consumed, and
which only ever tested English). This calls pipeline.run_turn() directly
against real seed data and scores the result against a rubric we define
ourselves, derived from the same policy logic the bot actually runs
(refund_matrix.py, abuse_rules.py) — not guessed expectations.

Every fixture below (customer_id, order_id, rider_id) is real data from
data/app.db, verified against the actual compute_abuse_signals() /
rider_incidents logic before being wired into a scenario — see the
comments on each scenario for how it was picked.

Usage:
    .venv/bin/python scripts/run_local_eval.py
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import db_session  # noqa: E402
from app.l1_cardinal.pipeline import run_turn  # noqa: E402
from app.migrations import bootstrap  # noqa: E402


@dataclass
class Scenario:
    id: str
    language: str
    message: str
    note: str
    expect_refund: bool
    expect_escalate: bool = False
    expect_flag_abuse: bool = False
    expect_complaint_target: str | None = None


@dataclass
class Result:
    scenario: Scenario
    detected_language: str
    actions: list[dict]
    bot_message: str
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


SCENARIOS = [
    # Clean customer (id=1, not flagged abuser), real order #1 (₹925 total,
    # Margherita pizza among the items). Missing-item refund matrix expects
    # ~50% of order total.
    Scenario(
        id="clean_missing_item_en",
        language="English",
        message=(
            "Hi, my order #1 arrived but the Margherita pizza was missing — "
            "everything else came fine."
        ),
        note="Control case: clean customer, straightforward missing-item claim.",
        expect_refund=True,
        expect_complaint_target="restaurant",
    ),
    # Same clean customer, different real order (#3, ₹1106 total), written
    # in Hindi — proves the pipeline resolves correctly (not just replies)
    # in a non-English language.
    Scenario(
        id="clean_never_arrived_hi",
        language="Hindi",
        message="नमस्ते, मेरा ऑर्डर #3 कभी नहीं आया, खाना डिलीवर ही नहीं हुआ।",
        note="Clean customer, never-arrived claim, in Hindi — should resolve identically to English.",
        expect_refund=True,
        expect_complaint_target="rider",
    ),
    # THE edge case. Customer #9 (Kabir Khan) is a REAL computed abuser —
    # complaint_rate=0.62, rejected_rate=0.80 via the actual
    # compute_abuse_signals() logic. Order #129 was delivered by rider #4
    # (Rahul Iyer), who has real verified "theft_claim" incidents (marked
    # delivered but customer never received it) on other orders. This is
    # the exact shape of the historical loophole: an abuser claiming
    # never-arrived against a rider who genuinely has a bad record. The
    # guardrail must refuse the refund regardless — same claim, three
    # languages, to prove the deterministic layer doesn't weaken under
    # Sarvam routing.
    Scenario(
        id="abuse_never_arrived_en",
        language="English",
        message="Hi, my order #129 never arrived, I never got my pizza.",
        note="Real computed abuser + real bad-record rider. Refund must be refused.",
        expect_refund=False,
        expect_escalate=True,
        expect_flag_abuse=True,
    ),
    Scenario(
        id="abuse_never_arrived_hi",
        language="Hindi",
        message="नमस्ते, मेरा ऑर्डर #129 कभी नहीं आया, मुझे पिज्जा नहीं मिला।",
        note="Same abuser/rider pair as above, in Hindi.",
        expect_refund=False,
        expect_escalate=True,
        expect_flag_abuse=True,
    ),
    Scenario(
        id="abuse_never_arrived_ta",
        language="Tamil",
        message="வணக்கம், எனது ஆர்டர் #129 வரவே இல்லை, எனக்கு பீட்சா கிடைக்கவில்லை.",
        note="Same abuser/rider pair, in Tamil — routes to Sarvam, not Gemini.",
        expect_refund=False,
        expect_escalate=True,
        expect_flag_abuse=True,
    ),
    # Double-charge force-routes to an app complaint with no LLM-judged
    # refund amount — a different deterministic rule than the abuse case.
    Scenario(
        id="double_charge_en",
        language="English",
        message="I think I was charged twice for order #2, can you check?",
        note="double_charge should force-route to an app complaint; Stage 1's own refund guess gets dropped.",
        expect_refund=False,
        expect_complaint_target="app",
    ),
]


def run_scenario(sc: Scenario) -> Result:
    session_id = f"local-eval-{sc.id}-{uuid.uuid4().hex[:8]}"
    with db_session() as db:
        tr = run_turn(
            db,
            session_id=session_id,
            customer_message=sc.message,
            mode="local_eval",
        )

    actions = tr.actions
    has_refund = any(a.get("type") == "issue_refund" for a in actions)
    has_escalate = any(a.get("type") == "escalate_to_human" for a in actions)
    has_flag = any(a.get("type") == "flag_abuse" for a in actions)
    complaint_targets = {a.get("target_type") for a in actions if a.get("type") == "file_complaint"}

    checks = {
        "refund": has_refund == sc.expect_refund,
        "escalate": has_escalate == sc.expect_escalate if sc.expect_escalate else True,
        "flag_abuse": has_flag == sc.expect_flag_abuse if sc.expect_flag_abuse else True,
    }
    if sc.expect_complaint_target:
        checks["complaint_target"] = sc.expect_complaint_target in complaint_targets

    return Result(
        scenario=sc,
        detected_language=tr.classification.get("detected_language", "?"),
        actions=actions,
        bot_message=tr.bot_message,
        checks=checks,
    )


def main() -> None:
    print("Bootstrapping seed data (idempotent, skips if already loaded)...")
    bootstrap.run()

    results = [run_scenario(sc) for sc in SCENARIOS]

    print("\n" + "=" * 78)
    print("INDEPENDENT LOCAL EVAL — quickbites-bot (Gemini + Sarvam, multilingual)")
    print("=" * 78)

    passed = 0
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        if r.passed:
            passed += 1
        print(f"\n[{status}] {r.scenario.id}  ({r.scenario.language})")
        print(f"  note:              {r.scenario.note}")
        print(f"  message:           {r.scenario.message}")
        print(f"  detected_language: {r.detected_language}")
        print(f"  bot_message:       {r.bot_message}")
        print(f"  actions:           {r.actions}")
        for check, ok in r.checks.items():
            print(f"    - {check}: {'ok' if ok else 'MISMATCH'}")

    total = len(results)
    print("\n" + "-" * 78)
    print(f"SCORE: {passed}/{total} scenarios passed ({passed / total * 100:.1f}%)")
    print("-" * 78 + "\n")


if __name__ == "__main__":
    main()
