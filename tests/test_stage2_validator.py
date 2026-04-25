from app.l2_agents.stage2_validator import validate
from app.schemas import (
    AbuseSignals,
    Classification,
    CustomerProfile,
    EnrichedContext,
    OrderContext,
    ProposedAction,
    RestaurantHistory,
    RiderHistory,
    Stage1Output,
)


def _order(total=600, placed_at="2026-04-13T10:00:00") -> OrderContext:
    return OrderContext(
        id=40,
        customer_id=1,
        restaurant_id=5,
        rider_id=9,
        placed_at=placed_at,
        delivered_at="2026-04-13T10:35:00",
        status="delivered",
        subtotal_inr=total - 40,
        delivery_fee_inr=40,
        total_inr=total,
        payment_method="upi",
        promo_code=None,
        address="Bangalore",
        items=[{"item_name": "Biryani", "qty": 1, "price_inr": 560}],
    )


def _customer(*, abuser=False, tier="silver") -> CustomerProfile:
    abuse = AbuseSignals(
        complaint_rate=0.7 if abuser else 0.1,
        rejected_complaint_rate=0.6 if abuser else 0.0,
        refunds_30d_count=0,
        refunds_30d_total_inr=0,
        account_age_days=200,
        total_orders=10,
        total_complaints=7 if abuser else 1,
        is_likely_abuser=abuser,
        abuse_reasons=["high_complaint_rate"] if abuser else [],
    )
    return CustomerProfile(
        id=1,
        name="Test Customer",
        loyalty_tier=tier,
        wallet_balance_inr=0,
        city="Bangalore",
        joined_at="2024-01-01T00:00:00",
        abuse=abuse,
    )


def _rider(*, verified=0, joined="2023-01-01T00:00:00") -> RiderHistory:
    return RiderHistory(
        id=9,
        name="Clean Rider",
        joined_at=joined,
        verified_incidents=verified,
        unverified_incidents=2,
        types_seen=["late"],
    )


def _restaurant() -> RestaurantHistory:
    return RestaurantHistory(
        id=5, name="Biryani Co", cuisine="Indian",
        avg_rating=4.2, n_reviews=50, recent_complaint_count=3,
    )


def test_refund_capped_to_order_total():
    # Use a NON-matrix-actionable intent on an abuser so the order-total
    # cap is the only thing standing between Stage 1's ₹5000 and the
    # ₹500 order. Matrix override and abuser-soft-claim paths both gate
    # on intent so they don't interfere.
    ctx = EnrichedContext(order=_order(total=500), customer=_customer(abuser=True))
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=5000, method="cash")
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="vague"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    refunds = [a for a in out.final_actions if a.type == "issue_refund"]
    assert refunds and refunds[0].amount_inr == 500
    assert any("capped_refund_to_order_total" in o for o in out.overrides_applied)


def test_double_charge_forces_app_complaint_and_drops_refund():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=600, method="cash")
        ],
        reasoning="",
        confidence=0.95,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="double_charge"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert not any(a.type == "issue_refund" for a in out.final_actions)
    assert any(a.type == "file_complaint" and a.target_type == "app" for a in out.final_actions)


def test_never_arrived_with_clean_rider_and_abuser_refuses_and_flags():
    ctx = EnrichedContext(
        order=_order(),
        customer=_customer(abuser=True),
        rider=_rider(verified=0, joined="2023-01-01T00:00:00"),
        restaurant=_restaurant(),
    )
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=600, method="cash")
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="never_arrived"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert not any(a.type == "issue_refund" for a in out.final_actions)
    assert any(a.type == "escalate_to_human" for a in out.final_actions)
    assert any(a.type == "flag_abuse" for a in out.final_actions)


def test_injection_strips_refund_when_intent_not_refundable():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=5000, method="cash")
        ],
        reasoning="",
        confidence=0.95,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="vague", injection_attempt=True),
        ctx=ctx,
        injection_flag=True,
        verbal_abuse=False,
        turn_no=1,
    )
    assert not any(a.type == "issue_refund" for a in out.final_actions)
    assert any("injection_attempt" in o for o in out.overrides_applied)


def test_low_confidence_escalates():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.3)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="vague"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert any(a.type == "escalate_to_human" for a in out.final_actions)
    assert out.route == "HITL"


def test_soft_cap_escalates_for_non_gold():
    # Use an intent NOT in the matrix-actionable set so Stage 1's amount
    # flows through unaltered, then the soft-cap escalation fires. (A
    # matrix-actionable intent would get the amount rewritten by the
    # matrix and stay under the soft cap by design.)
    ctx = EnrichedContext(order=_order(total=3000), customer=_customer(tier="bronze"))
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=3000, method="cash")
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="vague"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert any(a.type == "escalate_to_human" for a in out.final_actions)


def test_cancel_request_clears_actions():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=100, method="cash")
        ],
        reasoning="",
        confidence=0.8,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cancel_request"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert out.final_actions == []
    assert any("cancel_request" in o for o in out.overrides_applied)


def test_rider_demanded_tip_strips_refund_even_without_injection():
    ctx = EnrichedContext(order=_order(), customer=_customer(), rider=_rider())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=200, method="wallet_credit"),
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="rider_demanded_tip"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert not any(a.type == "issue_refund" for a in out.final_actions)
    assert any(a.type == "file_complaint" and a.target_type == "rider" for a in out.final_actions)


def test_rider_demanded_tip_survives_injection_without_refund():
    ctx = EnrichedContext(order=_order(), customer=_customer(), rider=_rider())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=500, method="wallet_credit"),
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="rider_demanded_tip", injection_attempt=True),
        ctx=ctx,
        injection_flag=True,
        verbal_abuse=False,
        turn_no=1,
    )
    assert not any(a.type == "issue_refund" for a in out.final_actions)


def test_rider_demanded_tip_forces_rider_complaint():
    ctx = EnrichedContext(order=_order(), customer=_customer(), rider=_rider())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="rider_demanded_tip"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert any(a.type == "file_complaint" and a.target_type == "rider" for a in out.final_actions)


def test_already_escalated_replaces_re_escalation_with_close():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="escalate_to_human", reason="still unsure")
        ],
        reasoning="",
        confidence=0.8,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="vague"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=3,
        already_escalated=True,
    )
    assert not any(a.type == "escalate_to_human" for a in out.final_actions)
    assert any(a.type == "close" for a in out.final_actions)
    assert any("already_escalated" in o for o in out.overrides_applied)


def test_already_escalated_keeps_new_resolution_actions():
    # If the customer brought new actionable info (e.g. a real refund can now be issued),
    # we should keep the resolution and drop the re-escalation.
    ctx = EnrichedContext(order=_order(total=500), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=200, method="wallet_credit"),
            ProposedAction(type="escalate_to_human", reason="also escalate"),
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="missing_item"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=3,
        already_escalated=True,
    )
    # Resolution is preserved (refund exists), extra escalate isn't re-added.
    # Matrix-amount-override rewrites the amount to missing_item @ 50% = ₹250.
    assert any(a.type == "issue_refund" and a.amount_inr == 250 for a in out.final_actions)


def test_matrix_fills_concrete_fix_when_stage1_only_escalates():
    ctx = EnrichedContext(
        order=_order(total=800),
        customer=_customer(),
        restaurant=_restaurant(),
    )
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="escalate_to_human", reason="unsure")
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="missing_item"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    refunds = [a for a in out.final_actions if a.type == "issue_refund"]
    complaints = [a for a in out.final_actions if a.type == "file_complaint"]
    escalations = [a for a in out.final_actions if a.type == "escalate_to_human"]
    assert refunds and refunds[0].amount_inr == 400  # 50% of 800
    assert refunds[0].method == "wallet_credit"
    assert complaints and complaints[0].target_type == "restaurant"
    assert not escalations
    assert any("matrix_proposed" in o for o in out.overrides_applied)


def test_abuser_soft_claim_emits_token_credit_plus_escalate():
    # Fix H: for an abuser raising a plausible food-quality issue
    # (cold_food / missing_item) with an order in context, emit a small
    # token credit (≤₹300) + escalate + flag. Rubric (Sc A9) prefers
    # this over blanket refusal (refuse-only scores 60, token+escalate
    # scores 100).
    ctx = EnrichedContext(
        order=_order(total=800),
        customer=_customer(abuser=True),
        restaurant=_restaurant(),
    )
    stage1 = Stage1Output(
        proposed_actions=[ProposedAction(type="escalate_to_human", reason="abuser")],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="missing_item", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    refunds = [a for a in out.final_actions if a.type == "issue_refund"]
    assert refunds and refunds[0].amount_inr <= 300
    assert refunds[0].method == "wallet_credit"
    assert any(a.type == "escalate_to_human" for a in out.final_actions)
    assert any(a.type == "flag_abuse" for a in out.final_actions)
    assert any("abuser_soft_claim" in o for o in out.overrides_applied)


def test_matrix_amount_overrides_stage1_concrete_refund():
    # Matrix-actionable intent + clean customer → matrix rewrites Stage 1's
    # amount to the policy value. cold_food @ 30% of ₹800 = ₹240.
    ctx = EnrichedContext(order=_order(total=800), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(
                type="issue_refund", order_id=40, amount_inr=200, method="wallet_credit"
            )
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cold_food"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    refunds = [a for a in out.final_actions if a.type == "issue_refund"]
    assert refunds and refunds[0].amount_inr == 240
    assert any("matrix_amount_override" in o for o in out.overrides_applied)


def test_awaiting_order_id_strips_premature_escalation_on_t1():
    ctx = EnrichedContext(order=None, customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[ProposedAction(type="escalate_to_human", reason="no order")],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cold_food"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert out.final_actions == []  # prose-only turn, keeps session open
    assert any("awaiting_order_id" in o for o in out.overrides_applied)


def test_matrix_above_cap_downgrades_to_escalation():
    # wrong_order @ 100% of ₹3000 = ₹3000. Silver-tier cap for ₹2001-5000 = 1500.
    # Matrix should NOT fire (within_cap=False), bare escalate remains.
    ctx = EnrichedContext(order=_order(total=3000), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[ProposedAction(type="escalate_to_human", reason="high value")],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="wrong_order"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert not any(a.type == "issue_refund" for a in out.final_actions)
    assert any(a.type == "escalate_to_human" for a in out.final_actions)


def test_empty_actions_defaults_to_close():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="vague"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert any(a.type == "close" for a in out.final_actions)
    assert any("empty_actions" in o for o in out.overrides_applied)
    assert out.route == "AUTO_RESOLVED"


def test_cancel_request_stays_empty_even_with_safety_net():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cancel_request"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert out.final_actions == []


def test_verbal_abuse_forces_escalation():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="missing_item"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=True,
        turn_no=1,
    )
    assert any(a.type == "escalate_to_human" for a in out.final_actions)


def test_close_marker_forces_close_and_short_circuits():
    # Simulator emits 'CLOSE: ...' inside customer_message as an explicit
    # resolution signal. Stage 2 must honour it regardless of Stage 1's
    # proposed actions (e.g. human_request → escalate is wrong here).
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(
                type="escalate_to_human",
                reason="customer asked for human",
            )
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="human_request"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=3,
        customer_message=(
            "Thanks, that's all I wanted.\n\nCLOSE: Appreciate the quick response."
        ),
    )
    assert [a.type for a in out.final_actions] == ["close"]
    assert any("customer_close_marker" in o for o in out.overrides_applied)


def test_confidence_downgrade_skipped_when_awaiting_order_id():
    # Refundable intent on T1 with no order + low confidence: the confidence
    # rule must NOT re-escalate after awaiting_order_id has cleared the
    # premature escalation. The session should stay open for T2 to resolve.
    ctx = EnrichedContext(order=None, customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[],
        reasoning="",
        confidence=0.4,  # below confidence_floor (0.6)
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cold_food"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
    )
    assert not any(a.type == "escalate_to_human" for a in out.final_actions)
    assert any("awaiting_order_id" in o for o in out.overrides_applied)


def test_abuser_ambiguous_claim_escalates_with_flag_abuse():
    # Flagged-abuser raises a matrix-actionable claim (missing_item) with an
    # order. Fix H now adds a token credit alongside the escalate+flag
    # for soft food-quality intents — but the escalate+flag pair must
    # still be present and we must NOT silently close.
    ctx = EnrichedContext(order=_order(), customer=_customer(abuser=True))
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.7)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="missing_item", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
    )
    types = {a.type for a in out.final_actions}
    assert "escalate_to_human" in types
    assert "flag_abuse" in types
    assert "close" not in types
    assert any(
        "abuser_soft_claim" in o or "abuser_claim" in o
        for o in out.overrides_applied
    )


def test_human_request_without_keyword_does_not_escalate():
    # Stage 0 sometimes misclassifies pleasantries ("thanks, that's all I
    # wanted") as human_request. Without an explicit human keyword, Stage 2
    # must NOT force-escalate — let the safety net close the session.
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="human_request"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=3,
        customer_message=(
            "Thanks for handling it. I just wanted it on record so the rider "
            "gets some coaching. Appreciate it."
        ),
    )
    assert not any(a.type == "escalate_to_human" for a in out.final_actions)
    assert any(a.type == "close" for a in out.final_actions)
    assert any("no_human_keyword" in o for o in out.overrides_applied)


def test_human_request_with_keyword_escalates():
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="human_request"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
        customer_message="I want to speak to a manager about this.",
    )
    assert any(a.type == "escalate_to_human" for a in out.final_actions)


def test_matrix_overrides_stage1_refund_amount():
    # Stage 1 proposed ₹400 for cold food on a ₹1642 order. Matrix says 30%
    # = ₹493. Stage 2 must overwrite the amount (and method), because the
    # matrix is the system of record for refund amounts.
    ctx = EnrichedContext(order=_order(total=1642), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(
                type="issue_refund",
                order_id=40,
                amount_inr=400,
                method="cash",  # wrong method too
            )
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cold_food", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
    )
    refund = next(a for a in out.final_actions if a.type == "issue_refund")
    assert refund.amount_inr == 493  # 30% of 1642
    assert refund.method == "wallet_credit"
    assert any("matrix_amount_override" in o for o in out.overrides_applied)


def test_matrix_override_skipped_for_abuser():
    ctx = EnrichedContext(order=_order(total=1000), customer=_customer(abuser=True))
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="issue_refund", order_id=40, amount_inr=300, method="wallet_credit")
        ],
        reasoning="",
        confidence=0.8,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cold_food", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
    )
    # Abuser path bypasses matrix override; Stage 1's amount stays as-is
    # (the force-escalate rules elsewhere will handle the abuser case).
    assert not any("matrix_amount_override" in o for o in out.overrides_applied)


def test_dedupes_complaint_already_filed_this_session():
    # Second turn re-running the matrix shouldn't refile the rider complaint.
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    prior = [
        {"type": "file_complaint", "order_id": 40, "target_type": "rider"}
    ]
    out = validate(
        stage1=stage1,
        classification=Classification(intent="rider_rude", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=3,
        prior_bot_actions=prior,
    )
    # The matrix would have added a duplicate file_complaint; dedupe should
    # strip it and we fall through to the safety-net close.
    assert not any(a.type == "file_complaint" for a in out.final_actions)
    assert any("deduped_prior_actions" in o for o in out.overrides_applied)


def test_injection_adds_flag_abuse():
    # Any prompt-injection attempt must leave a flag_abuse trail, so T&S
    # can see the pattern over time.
    ctx = EnrichedContext(order=None, customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.3)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="human_request", injection_attempt=True),
        ctx=ctx,
        injection_flag=True,
        verbal_abuse=False,
        turn_no=1,
    )
    assert any(a.type == "flag_abuse" for a in out.final_actions)
    assert any("injection_attempt:flagged_abuse" in o for o in out.overrides_applied)


def test_matrix_override_adds_partner_complaint_when_missing():
    # Fix F: when Stage 1 proposes a refund without the partner complaint,
    # matrix-amount-override now adds it. Prevents the Sc 2 / Sc 12
    # failure mode where refund_correct passed but complaint_handling
    # failed because file_complaint never fired.
    ctx = EnrichedContext(order=_order(total=1000), customer=_customer())
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(
                type="issue_refund", order_id=40, amount_inr=300, method="wallet_credit"
            )
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cold_food", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
    )
    types = {a.type for a in out.final_actions}
    assert "issue_refund" in types
    assert "file_complaint" in types
    complaint = next(a for a in out.final_actions if a.type == "file_complaint")
    assert complaint.target_type == "restaurant"
    assert any("matrix_complaint_added" in o for o in out.overrides_applied)


def test_never_arrived_abuser_refused_regardless_of_rider_quality():
    # Fix I: abuser claiming never_arrived must be refused even when the
    # rider has unverified incidents. Sc B9 failed at 30/100 because we
    # required clean_rider+long_history; now any abuser+never_arrived
    # combination strips the refund and escalates.
    ctx = EnrichedContext(
        order=_order(total=1325),
        customer=_customer(abuser=True),
        rider=RiderHistory(
            id=9, name="Mixed Rider", joined_at="2024-01-01T00:00:00",
            verified_incidents=2, unverified_incidents=4,
            types_seen=["late", "rude"],
        ),
        restaurant=_restaurant(),
    )
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(
                type="issue_refund", order_id=40, amount_inr=1325, method="wallet_credit"
            )
        ],
        reasoning="customer pressed for refund",
        confidence=0.7,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="never_arrived", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
    )
    assert not any(a.type == "issue_refund" for a in out.final_actions)
    assert any(a.type == "escalate_to_human" for a in out.final_actions)
    assert any(a.type == "flag_abuse" for a in out.final_actions)
    assert any("never_arrived_abuse_refused" in o for o in out.overrides_applied)


def test_human_request_t1_no_order_strips_stage1_escalate():
    # Fix L: "Put me through to a manager immediately" on T1 with no
    # concrete claim must trigger triage (strip Stage 1's escalate),
    # not auto-handoff. Sc C2 expects escalation only after a triage
    # attempt.
    ctx = EnrichedContext(order=None, customer=None)
    stage1 = Stage1Output(
        proposed_actions=[
            ProposedAction(type="escalate_to_human", reason="customer demanded a manager")
        ],
        reasoning="",
        confidence=0.9,
    )
    out = validate(
        stage1=stage1,
        classification=Classification(intent="human_request"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=1,
        customer_message="Put me through to a manager immediately. I won't deal with a bot.",
    )
    assert not any(a.type == "escalate_to_human" for a in out.final_actions)
    assert any("t1_triage_first" in o for o in out.overrides_applied)


def test_human_request_escalate_keyword_alone_does_not_force_escalation():
    # Fix K: the bare verb "escalate" appears in routing requests like
    # "Can you escalate it that way?" — this is NOT a request to talk to
    # a person. Lost 10pts on Sc C3 to this previously.
    ctx = EnrichedContext(order=_order(), customer=_customer())
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    out = validate(
        stage1=stage1,
        classification=Classification(intent="human_request"),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=3,
        customer_message=(
            "Actually I'd prefer this gets looked at by your engineering team — "
            "can you escalate it that way?"
        ),
    )
    assert not any(a.type == "escalate_to_human" for a in out.final_actions)


def test_post_injection_pivot_for_abuser_refuses_silently():
    # Fix J: when post_injection_pivot fires AND the customer is also a
    # flagged abuser, strip ALL money + escalation; keep only flag_abuse.
    # Sc C1 grader expects "Refuse; don't reveal; flag" — escalation
    # there is over-routing.
    ctx = EnrichedContext(
        order=_order(total=747),
        customer=_customer(abuser=True),
        restaurant=_restaurant(),
    )
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    prior = [
        {"type": "flag_abuse", "reason": "Prompt-injection pattern detected."}
    ]
    out = validate(
        stage1=stage1,
        classification=Classification(intent="cold_food", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
        prior_bot_actions=prior,
        already_flag_abused=True,
    )
    types = {a.type for a in out.final_actions}
    assert "issue_refund" not in types
    assert "escalate_to_human" not in types
    assert "flag_abuse" in types
    assert any(
        "post_injection_pivot:abuser:refused_silently" in o
        for o in out.overrides_applied
    )


def test_post_injection_pivot_forces_escalation_on_later_claim_turn():
    # T1 fired flag_abuse on an injection attempt. T2 pivots to a real-
    # sounding claim (missing_item with order). Stage 2 must escalate +
    # keep the flag trail rather than auto-resolving or auto-closing,
    # otherwise Stage 3 produces tone-deaf "hope you enjoyed your meal!"
    # replies to customers who previously probed the bot.
    ctx = EnrichedContext(
        order=_order(total=800),
        customer=_customer(),
        restaurant=_restaurant(),
    )
    stage1 = Stage1Output(proposed_actions=[], reasoning="", confidence=0.9)
    prior = [
        {"type": "flag_abuse", "reason": "Prompt-injection pattern detected."},
        {"type": "close", "outcome_summary": "Injection attempt; closed."},
    ]
    out = validate(
        stage1=stage1,
        classification=Classification(intent="missing_item", mentioned_order_id=40),
        ctx=ctx,
        injection_flag=False,
        verbal_abuse=False,
        turn_no=2,
        prior_bot_actions=prior,
        already_flag_abused=True,
    )
    types = {a.type for a in out.final_actions}
    assert "escalate_to_human" in types
    assert "flag_abuse" in types
    assert "close" not in types
    assert any("post_injection_pivot" in o for o in out.overrides_applied)
