from app.policies.abuse_rules import compute_abuse_signals, has_clean_history


def test_clean_silver_customer_is_not_flagged():
    signals = compute_abuse_signals(
        joined_at="2024-01-01T00:00:00",
        total_orders=20,
        total_complaints=2,
        rejected_complaints=0,
        refunds_30d_count=0,
        refunds_30d_total_inr=0,
    )
    assert signals.is_likely_abuser is False
    assert signals.abuse_reasons == []
    assert has_clean_history(signals)


def test_myra_9_of_9_rejected_is_flagged():
    # Matches customer 49 Myra Kulkarni in app.db: 9 orders, 9 complaints, all rejected.
    signals = compute_abuse_signals(
        joined_at="2025-11-05T18:35:00",
        total_orders=9,
        total_complaints=9,
        rejected_complaints=9,
        refunds_30d_count=0,
        refunds_30d_total_inr=0,
    )
    assert signals.is_likely_abuser is True
    assert any("complaint_rate" in r for r in signals.abuse_reasons)


def test_brand_new_complainer_flagged():
    # Joined <30 days before DATA_TODAY (2026-04-13) and already 2 complaints.
    signals = compute_abuse_signals(
        joined_at="2026-04-01T00:00:00",
        total_orders=3,
        total_complaints=2,
        rejected_complaints=0,
        refunds_30d_count=0,
        refunds_30d_total_inr=0,
    )
    assert signals.is_likely_abuser is True
    assert any("account_age" in r for r in signals.abuse_reasons)


def test_refund_flooded_with_rejection_flagged():
    # ₹2500 over 3 events alone would NOT flag (Fix G), but a single prior
    # rejection corroborates the money signal and trips it.
    signals = compute_abuse_signals(
        joined_at="2024-01-01T00:00:00",
        total_orders=30,
        total_complaints=5,
        rejected_complaints=1,
        refunds_30d_count=3,
        refunds_30d_total_inr=2500,
    )
    assert signals.is_likely_abuser is True
    assert any("refunds_30d" in r for r in signals.abuse_reasons)


def test_refund_flooded_high_event_count_flagged():
    # 4+ refund events + ₹>2000 also corroborates without needing rejections.
    signals = compute_abuse_signals(
        joined_at="2024-01-01T00:00:00",
        total_orders=30,
        total_complaints=4,
        rejected_complaints=0,
        refunds_30d_count=4,
        refunds_30d_total_inr=2500,
    )
    assert signals.is_likely_abuser is True


def test_gold_customer_with_legit_refund_history_not_flagged():
    # Aryan Pillai, customer 8 in app.db: gold tier, ₹2138 across 3 events,
    # zero rejections. Sc A3 in prod failed at 30/100 because the old
    # heuristic flagged him purely on the ₹2138 > 2000 threshold and the
    # bot escalated+flagged what was actually a legitimate complaint.
    # Fix G: bare high-spend with zero rejection history does NOT flag.
    signals = compute_abuse_signals(
        joined_at="2023-06-01T00:00:00",
        total_orders=40,
        total_complaints=4,
        rejected_complaints=0,
        refunds_30d_count=3,
        refunds_30d_total_inr=2138,
    )
    assert signals.is_likely_abuser is False
    assert signals.abuse_reasons == []
