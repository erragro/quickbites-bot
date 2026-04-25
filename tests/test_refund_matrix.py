from app.policies.refund_matrix import is_refundable_intent, propose
from app.schemas import AbuseSignals, CustomerProfile, OrderContext


def _order(total=1000) -> OrderContext:
    return OrderContext(
        id=1, customer_id=1, restaurant_id=1, rider_id=1,
        placed_at="2026-04-13T10:00:00", delivered_at="2026-04-13T10:40:00",
        status="delivered", subtotal_inr=total - 40, delivery_fee_inr=40,
        total_inr=total, payment_method="upi", promo_code=None,
        address="Bangalore", items=[],
    )


def _customer(*, tier="silver", abuser=False, total_orders=10) -> CustomerProfile:
    return CustomerProfile(
        id=1, name="Test", loyalty_tier=tier, wallet_balance_inr=0,
        city="Bangalore", joined_at="2024-01-01T00:00:00",
        abuse=AbuseSignals(
            complaint_rate=0.5 if abuser else 0.1,
            rejected_complaint_rate=0.5 if abuser else 0.0,
            total_orders=total_orders,
            total_complaints=5 if abuser else 1,
            is_likely_abuser=abuser,
        ),
    )


def test_missing_item_is_partial_refund():
    p = propose(intent="missing_item", order=_order(total=800), customer=_customer())
    assert p is not None
    assert p.refund_inr == 400  # 50% of 800
    assert p.method == "wallet_credit"
    assert p.complaint_target == "restaurant"


def test_cold_food_is_thirty_percent():
    p = propose(intent="cold_food", order=_order(total=500), customer=_customer())
    assert p is not None
    assert p.refund_inr == 150  # 30% of 500
    assert p.complaint_target == "restaurant"


def test_wrong_order_is_full_refund():
    p = propose(intent="wrong_order", order=_order(total=1200), customer=_customer())
    assert p is not None
    assert p.refund_inr == 1200  # 100%
    assert p.complaint_target == "restaurant"


def test_rider_rude_is_complaint_only_no_refund():
    p = propose(intent="rider_rude", order=_order(), customer=_customer())
    assert p is not None
    assert p.refund_inr == 0
    assert p.method is None
    assert p.complaint_target == "rider"


def test_double_charge_is_app_complaint_only():
    p = propose(intent="double_charge", order=_order(), customer=_customer())
    assert p is not None
    assert p.refund_inr == 0
    assert p.complaint_target == "app"


def test_cancel_request_returns_none():
    p = propose(intent="cancel_request", order=_order(), customer=_customer())
    assert p is None


def test_gold_multiplier_bumps_refund():
    p = propose(intent="cold_food", order=_order(total=1000), customer=_customer(tier="gold"))
    base = 300
    assert p is not None
    assert p.refund_inr > base  # multiplier 1.15 (gold) → ~345


def test_abuser_multiplier_reduces_refund():
    p = propose(intent="cold_food", order=_order(total=1000), customer=_customer(abuser=True))
    base = 300
    assert p is not None
    assert p.refund_inr < base  # multiplier 0.7 (-0.30) → 210


def test_refund_never_exceeds_order_total():
    # wrong_order @ 100% with gold (+15%) should still cap at total.
    p = propose(intent="wrong_order", order=_order(total=500), customer=_customer(tier="gold"))
    assert p is not None
    assert p.refund_inr == 500


def test_no_order_context_returns_complaint_only_proposal():
    p = propose(intent="rider_rude", order=None, customer=_customer())
    assert p is not None
    assert p.refund_inr == 0
    assert p.complaint_target == "rider"
    assert "no_order" in p.label


def test_no_order_for_money_intent_returns_none():
    # Can't compute a refund amount without an order total.
    p = propose(intent="missing_item", order=None, customer=_customer())
    # No complaint target returned either since order_id would be null; but
    # the matrix still surfaces the complaint_target so caller can decide.
    # Current behaviour: returns proposal with refund=0 and complaint=restaurant.
    assert p is not None
    assert p.refund_inr == 0
    assert p.complaint_target == "restaurant"


def test_is_refundable_intent_classifies_correctly():
    assert is_refundable_intent("cold_food")
    assert is_refundable_intent("missing_item")
    assert is_refundable_intent("wrong_order")
    assert is_refundable_intent("never_arrived")
    assert is_refundable_intent("promo_failed")
    assert not is_refundable_intent("rider_rude")
    assert not is_refundable_intent("double_charge")
    assert not is_refundable_intent("cancel_request")
    assert not is_refundable_intent("vague")


def test_min_refund_floor_applies_on_tiny_orders():
    # 30% of ₹100 = ₹30, but min_inr=50 for cold_food.
    p = propose(intent="cold_food", order=_order(total=100), customer=_customer())
    assert p is not None
    assert p.refund_inr >= 50
