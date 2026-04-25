"""
Idempotent bootstrap: create schema, load app.db rows into Postgres if empty,
create our runtime tables (sessions, turns, bot_executions).

Types intentionally follow the SQLite source: dates are stored as TEXT (ISO-8601)
so the migration is a straight copy. All "recent" math in abuse_rules.py works
against the pinned DATA_TODAY constant in config.py.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from sqlalchemy import text

from app.config import SQLITE_SEED_PATH
from app.db import engine


logger = logging.getLogger(__name__)

SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS customers (
        id integer PRIMARY KEY,
        name text NOT NULL,
        phone text,
        email text,
        city text,
        joined_at text,
        loyalty_tier text,
        wallet_balance_inr integer
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS restaurants (
        id integer PRIMARY KEY,
        name text NOT NULL,
        cuisine text,
        city text,
        area text,
        joined_at text
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS riders (
        id integer PRIMARY KEY,
        name text NOT NULL,
        phone text,
        city text,
        joined_at text
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id integer PRIMARY KEY,
        customer_id integer REFERENCES customers(id),
        restaurant_id integer REFERENCES restaurants(id),
        rider_id integer REFERENCES riders(id),
        placed_at text,
        delivered_at text,
        status text,
        subtotal_inr integer,
        delivery_fee_inr integer,
        total_inr integer,
        payment_method text,
        promo_code text,
        address text
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS order_items (
        id integer PRIMARY KEY,
        order_id integer REFERENCES orders(id),
        item_name text,
        qty integer,
        price_inr integer
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS complaints (
        id integer PRIMARY KEY,
        customer_id integer REFERENCES customers(id),
        order_id integer REFERENCES orders(id),
        target_type text,
        target_id integer,
        raised_at text,
        description text,
        status text,
        resolution text,
        resolution_amount_inr integer
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS refunds (
        id integer PRIMARY KEY,
        customer_id integer REFERENCES customers(id),
        order_id integer REFERENCES orders(id),
        amount_inr integer,
        type text,
        issued_at text,
        reason text
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id integer PRIMARY KEY,
        customer_id integer REFERENCES customers(id),
        order_id integer REFERENCES orders(id),
        restaurant_id integer REFERENCES restaurants(id),
        rating integer,
        comment text,
        created_at text
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS rider_incidents (
        id integer PRIMARY KEY,
        rider_id integer REFERENCES riders(id),
        order_id integer REFERENCES orders(id),
        type text,
        reported_at text,
        verified integer,
        notes text
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id text PRIMARY KEY,
        simulator_session_id text UNIQUE,
        mode text,
        scenario_id integer,
        max_turns integer,
        known_order_id integer,
        known_customer_id integer,
        opened_at timestamptz DEFAULT now(),
        closed_at timestamptz,
        close_reason text,
        final_score jsonb
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS turns (
        id serial PRIMARY KEY,
        session_id text REFERENCES sessions(session_id),
        turn_no integer NOT NULL,
        role text NOT NULL,
        message text,
        classification jsonb,
        actions jsonb,
        reasoning text,
        route text,
        escalation_group text,
        execution_id text,
        stage_timings_ms jsonb,
        created_at timestamptz DEFAULT now()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bot_executions (
        execution_id text PRIMARY KEY,
        session_id text REFERENCES sessions(session_id),
        turn_no integer,
        escalation_group text,
        priority text,
        created_at timestamptz DEFAULT now()
    );
    """,
]

STARTER_TABLES = [
    "customers", "restaurants", "riders", "orders", "order_items",
    "complaints", "refunds", "reviews", "rider_incidents",
]


def _create_schema() -> None:
    with engine.begin() as conn:
        for ddl in SCHEMA_DDL:
            conn.execute(text(ddl))


def _table_is_empty(table: str) -> bool:
    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
    return count == 0


def _copy_sqlite_table(table: str, sqlite_path: Path) -> int:
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in src.execute(f"SELECT * FROM {table}").fetchall()]
    finally:
        src.close()

    if not rows:
        return 0

    cols = list(rows[0].keys())
    col_list = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    stmt = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})")

    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def run(force: bool = False) -> dict:
    if not SQLITE_SEED_PATH.exists():
        raise FileNotFoundError(f"Missing seed db at {SQLITE_SEED_PATH}")

    _create_schema()
    loaded: dict[str, int] = {}
    for table in STARTER_TABLES:
        if force or _table_is_empty(table):
            loaded[table] = _copy_sqlite_table(table, SQLITE_SEED_PATH)
        else:
            loaded[table] = 0
    logger.info("bootstrap complete: %s", loaded)
    return loaded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
