"""
Stage 1 tool definitions for Anthropic tool-use. Each tool is backed by a
repository function. The model uses these to re-query details the Phase 4
Enricher didn't pre-fetch (e.g. a second order_id the customer mentions later).
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app import repository


TOOL_SCHEMAS = [
    {
        "name": "get_order",
        "description": "Fetch an order with its line items by order_id.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_customer_profile",
        "description": (
            "Fetch a customer profile with precomputed abuse signals "
            "(complaint_rate, rejected_rate, refunds_30d, account_age_days, is_likely_abuser)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_rider_history",
        "description": "Verified vs unverified incident counts and types for a rider.",
        "input_schema": {
            "type": "object",
            "properties": {"rider_id": {"type": "integer"}},
            "required": ["rider_id"],
        },
    },
    {
        "name": "get_restaurant_history",
        "description": "Average rating, review count, recent complaint count for a restaurant.",
        "input_schema": {
            "type": "object",
            "properties": {"restaurant_id": {"type": "integer"}},
            "required": ["restaurant_id"],
        },
    },
    {
        "name": "get_customer_complaints",
        "description": "Recent complaints filed by the customer (status, resolution).",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_customer_refunds",
        "description": "Refunds issued to the customer within the last N days (default 30).",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"},
                "since_days": {"type": "integer", "default": 30},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_rider_incidents_for_order",
        "description": "Any rider incidents logged against a specific order.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    },
]


def dispatch(db: Session, name: str, args: dict) -> str:
    if name == "get_order":
        order = repository.fetch_order(db, args["order_id"])
        result = order.model_dump() if order else {"error": "not_found"}
    elif name == "get_customer_profile":
        cust = repository.fetch_customer(db, args["customer_id"])
        result = cust.model_dump() if cust else {"error": "not_found"}
    elif name == "get_rider_history":
        rider = repository.fetch_rider_history(db, args["rider_id"])
        result = rider.model_dump() if rider else {"error": "not_found"}
    elif name == "get_restaurant_history":
        r = repository.fetch_restaurant_history(db, args["restaurant_id"])
        result = r.model_dump() if r else {"error": "not_found"}
    elif name == "get_customer_complaints":
        result = repository.fetch_customer_complaints(
            db, args["customer_id"], args.get("limit", 10)
        )
    elif name == "get_customer_refunds":
        result = repository.fetch_customer_refunds(
            db, args["customer_id"], args.get("since_days", 30)
        )
    elif name == "get_rider_incidents_for_order":
        result = repository.fetch_rider_incidents_for_order(db, args["order_id"])
    else:
        result = {"error": f"unknown_tool:{name}"}

    return json.dumps(result, default=str)
