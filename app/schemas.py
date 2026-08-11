from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


ActionType = Literal["issue_refund", "file_complaint", "escalate_to_human", "flag_abuse", "close"]
RefundMethod = Literal["cash", "wallet_credit"]
ComplaintTarget = Literal["restaurant", "rider", "app"]


class IssueRefundAction(BaseModel):
    type: Literal["issue_refund"] = "issue_refund"
    order_id: int
    amount_inr: int = Field(ge=1)
    method: RefundMethod


class FileComplaintAction(BaseModel):
    type: Literal["file_complaint"] = "file_complaint"
    order_id: int
    target_type: ComplaintTarget


class EscalateAction(BaseModel):
    type: Literal["escalate_to_human"] = "escalate_to_human"
    reason: str


class FlagAbuseAction(BaseModel):
    type: Literal["flag_abuse"] = "flag_abuse"
    reason: str


class CloseAction(BaseModel):
    type: Literal["close"] = "close"
    outcome_summary: str


Action = Union[
    IssueRefundAction,
    FileComplaintAction,
    EscalateAction,
    FlagAbuseAction,
    CloseAction,
]


class SimulatorStartResponse(BaseModel):
    session_id: str
    mode: str
    scenario_id: int
    customer_message: str
    max_turns: int


class SimulatorReplyRequest(BaseModel):
    bot_message: str
    actions: list[dict] = Field(default_factory=list)


class SimulatorReplyResponse(BaseModel):
    customer_message: Optional[str] = None
    done: bool = False
    close_reason: Optional[str] = None
    score: Optional[dict] = None
    turns_remaining: Optional[int] = None


Intent = Literal[
    "missing_item",
    "wrong_order",
    "cold_food",
    "rider_late",
    "rider_rude",
    "rider_demanded_tip",
    "never_arrived",
    "double_charge",
    "promo_failed",
    "cancel_request",
    "human_request",
    "vague",
    "other",
]


class Classification(BaseModel):
    intent: Intent = "vague"
    mentioned_order_id: Optional[int] = None
    sentiment: Literal["angry", "frustrated", "neutral", "polite"] = "neutral"
    injection_attempt: bool = False
    verbal_abuse: bool = False
    detected_language: str = "en"


class AbuseSignals(BaseModel):
    complaint_rate: float = 0.0
    rejected_complaint_rate: float = 0.0
    refunds_30d_count: int = 0
    refunds_30d_total_inr: int = 0
    account_age_days: int = 0
    total_orders: int = 0
    total_complaints: int = 0
    is_likely_abuser: bool = False
    abuse_reasons: list[str] = Field(default_factory=list)


class CustomerProfile(BaseModel):
    id: int
    name: str
    loyalty_tier: Literal["bronze", "silver", "gold"]
    wallet_balance_inr: int
    city: str
    joined_at: str
    abuse: AbuseSignals


class OrderContext(BaseModel):
    id: int
    customer_id: int
    restaurant_id: int
    rider_id: Optional[int]
    placed_at: str
    delivered_at: Optional[str]
    status: str
    subtotal_inr: int
    delivery_fee_inr: int
    total_inr: int
    payment_method: str
    promo_code: Optional[str]
    address: str
    items: list[dict]


class RiderHistory(BaseModel):
    id: int
    name: str
    joined_at: str
    verified_incidents: int
    unverified_incidents: int
    types_seen: list[str]


class RestaurantHistory(BaseModel):
    id: int
    name: str
    cuisine: str
    avg_rating: Optional[float]
    n_reviews: int
    recent_complaint_count: int


class EnrichedContext(BaseModel):
    order: Optional[OrderContext] = None
    customer: Optional[CustomerProfile] = None
    rider: Optional[RiderHistory] = None
    restaurant: Optional[RestaurantHistory] = None


class ProposedAction(BaseModel):
    type: ActionType
    order_id: Optional[int] = None
    amount_inr: Optional[int] = None
    method: Optional[RefundMethod] = None
    target_type: Optional[ComplaintTarget] = None
    reason: Optional[str] = None
    outcome_summary: Optional[str] = None


class Stage1Output(BaseModel):
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    escalation_hint: Optional[str] = None


Route = Literal["AUTO_RESOLVED", "HITL", "MANUAL_REVIEW"]


class Stage2Output(BaseModel):
    final_actions: list[ProposedAction]
    route: Route
    overrides_applied: list[str] = Field(default_factory=list)


class Stage3Output(BaseModel):
    bot_message: str
    actions: list[dict]


EscalationGroup = Literal["FRAUD_REVIEW", "VIP_CONCIERGE", "REPEAT_ESCALATION", "STANDARD"]
Priority = Literal["CRITICAL", "HIGH", "STANDARD", "LOW"]
