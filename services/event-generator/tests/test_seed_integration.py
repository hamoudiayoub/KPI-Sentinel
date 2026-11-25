"""Loads the reference data into a real Postgres with the ERP schema (Testcontainers)."""

import pytest

from sentinel_gen import db
from sentinel_gen.reference import COLUMNS
from sentinel_gen.seed import ExistingDataError, seed

pytestmark = pytest.mark.integration


def fingerprints(conn):
    return {table: db.fingerprint(conn, table) for table in COLUMNS}


def test_seed_loads_every_reference_table(conn, config):
    counts = seed(conn, config, seed_value=42, force=True)
    for table, expected in counts.items():
        assert conn.execute(f"SELECT count(*) FROM erp.{table}").fetchone()[0] == expected


def test_seed_refuses_to_overwrite_without_force(conn, config):
    seed(conn, config, seed_value=42, force=True)
    with pytest.raises(ExistingDataError, match="--force"):
        seed(conn, config, seed_value=42, force=False)


def test_the_same_seed_gives_identical_fingerprints(conn, config):
    seed(conn, config, seed_value=42, force=True)
    first = fingerprints(conn)
    seed(conn, config, seed_value=42, force=True)
    assert fingerprints(conn) == first


def test_another_seed_changes_the_fingerprints(conn, config):
    seed(conn, config, seed_value=42, force=True)
    first = fingerprints(conn)
    seed(conn, config, seed_value=7, force=True)
    assert fingerprints(conn)["customers"] != first["customers"]


def test_identity_sequences_continue_after_the_loaded_ids(conn, config):
    seed(conn, config, seed_value=42, force=True)
    with conn.transaction():
        new_id = conn.execute(
            "INSERT INTO erp.brands (name) VALUES ('Test brand') RETURNING id"
        ).fetchone()[0]
        assert new_id == len(config.brands) + 1
        conn.execute("DELETE FROM erp.brands WHERE id = %s", (new_id,))


def test_channel_split_in_the_database_matches_the_configuration(conn, config):
    seed(conn, config, seed_value=42, force=True)
    rows = conn.execute("SELECT channel, count(*) FROM erp.customers GROUP BY channel").fetchall()
    for channel, count in rows:
        assert abs(count / config.customers - config.channels[channel].share) <= 0.02
