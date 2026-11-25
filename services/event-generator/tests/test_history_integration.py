"""Loads a short history into a real Postgres with the ERP schema (Testcontainers)."""

from datetime import date

import psycopg
import pytest

from sentinel_gen import db
from sentinel_gen.calendar import load_calendar
from sentinel_gen.history import ExistingHistoryError, backfill
from sentinel_gen.seed import seed

pytestmark = pytest.mark.integration

END = date(2026, 4, 1)  # two months that include the end of Ramadan and Eid al-Fitr


def run(conn, config, force=True, seed_value=42):
    return backfill(conn, config, load_calendar(), seed_value, 2, 0.02, END, force)


@pytest.fixture
def seeded(conn, config):
    seed(conn, config, seed_value=42, force=True)
    return conn


def test_backfill_loads_a_consistent_history(seeded, config):
    totals = run(seeded, config)
    assert totals["orders"] > 0
    assert totals["order_lines"] > totals["orders"]
    counts = {
        table: seeded.execute(f"SELECT count(*) FROM erp.{table}").fetchone()[0]
        for table in ("orders", "order_lines", "deliveries", "returns")
    }
    assert counts == {k: totals[k] for k in counts}
    # Statuses agree with the deliveries written alongside the orders.
    mismatched = seeded.execute(
        "SELECT count(*) FROM erp.orders o LEFT JOIN erp.deliveries d ON d.order_id = o.id "
        "WHERE (o.confirmed_at IS NOT NULL) <> (d.id IS NOT NULL) "
        "OR (o.status = 'CANCELLED' AND d.status <> 'FAILED')"
    ).fetchone()[0]
    assert mismatched == 0


def test_months_are_committed_one_by_one(seeded, config, postgres):
    run(seeded, config)
    with psycopg.connect(postgres.conninfo(), password="test-only") as other:
        months = other.execute(
            "SELECT count(DISTINCT date_trunc('month', placed_at)) FROM erp.orders"
        ).fetchone()[0]
    assert months == 2


def test_backfill_refuses_to_overwrite_without_force(seeded, config):
    run(seeded, config)
    with pytest.raises(ExistingHistoryError, match="--force"):
        run(seeded, config, force=False)


def test_the_same_seed_gives_identical_fingerprints(seeded, config):
    tables = ("price_changes", "promotions", "orders", "order_lines", "deliveries", "returns")
    run(seeded, config)
    first = {t: db.fingerprint(seeded, t) for t in tables}
    run(seeded, config)
    assert {t: db.fingerprint(seeded, t) for t in tables} == first


def test_product_prices_end_at_the_latest_price_change(seeded, config):
    run(seeded, config)
    stale = seeded.execute(
        "SELECT count(*) FROM erp.products p JOIN LATERAL ("
        "  SELECT list_price FROM erp.price_changes c WHERE c.product_id = p.id "
        "  ORDER BY effective_from DESC LIMIT 1) latest ON true "
        "WHERE latest.list_price <> p.list_price"
    ).fetchone()[0]
    assert stale == 0
