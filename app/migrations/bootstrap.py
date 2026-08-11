"""
Idempotent startup: create starter-data schema, load app.db rows into
Postgres if empty, then run Alembic migrations for the runtime tables
(sessions, turns, bot_executions, users).

Split of responsibilities:
- STARTER schema (this file) — read-only snapshot from data/app.db. Loaded via
  raw SQL because Alembic doesn't help with a fixed-forever data table.
- RUNTIME schema (alembic/versions/) — tables the app writes to every turn
  plus the auth tables. Version-controlled and rollback-able.

Types intentionally follow the SQLite source: dates are stored as TEXT
(ISO-8601) so the copy is 1:1. All "recent" math in abuse_rules.py works
against the pinned DATA_TODAY constant in config.py.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text

from app.config import PROJECT_ROOT, SQLITE_SEED_PATH
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
    # Runtime tables (sessions, turns, bot_executions, users) live in
    # alembic/versions/ — see _run_migrations() below.
]

STARTER_TABLES = [
    "customers", "restaurants", "riders", "orders", "order_items",
    "complaints", "refunds", "reviews", "rider_incidents",
]


def _create_schema() -> None:
    with engine.begin() as conn:
        for ddl in SCHEMA_DDL:
            conn.execute(text(ddl))


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :n)"
        ),
        {"n": name},
    ).scalar_one()


def _run_migrations() -> str:
    """
    Apply pending Alembic migrations.

    Legacy-DB handling: if `sessions` etc. already exist (created by the old
    bootstrap.py before Alembic was introduced) but there's no
    `alembic_version` row, we stamp the DB at revision 001 so the initial
    migration is not re-applied against tables that are already there. Any
    subsequent revisions run normally on top.

    Returns the current head revision after migration for logging.
    """
    cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))

    with engine.begin() as conn:
        has_alembic = _table_exists(conn, "alembic_version")
        has_sessions = _table_exists(conn, "sessions")

    if has_sessions and not has_alembic:
        logger.info("legacy DB detected (sessions exists, no alembic_version); stamping at 001")
        command.stamp(cfg, "001")

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    return head or "unknown"


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
    """
    Full startup path:
      1. Create starter-data schema (customers, orders, riders, restaurants, …)
      2. Copy starter rows from data/app.db into Postgres if empty
      3. Apply Alembic migrations for runtime + auth tables

    Order matters: starter schema first so any FK from a runtime table to a
    starter table would still resolve; Alembic runs last so schema evolution
    can safely assume both layers exist.
    """
    if not SQLITE_SEED_PATH.exists():
        raise FileNotFoundError(f"Missing seed db at {SQLITE_SEED_PATH}")

    _create_schema()
    loaded: dict[str, int] = {}
    for table in STARTER_TABLES:
        if force or _table_is_empty(table):
            loaded[table] = _copy_sqlite_table(table, SQLITE_SEED_PATH)
        else:
            loaded[table] = 0

    alembic_head = _run_migrations()
    logger.info("bootstrap complete: seed=%s alembic_head=%s", loaded, alembic_head)
    return {"seed": loaded, "alembic_head": alembic_head}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
