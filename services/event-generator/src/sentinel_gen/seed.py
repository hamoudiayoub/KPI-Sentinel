"""Loads the reference data into an empty ERP, in one transaction."""

from __future__ import annotations

import logging

import psycopg

from sentinel_gen import db
from sentinel_gen.config import MarketConfig
from sentinel_gen.logs import log
from sentinel_gen.reference import COLUMNS, LOAD_ORDER, generate_reference_data

logger = logging.getLogger(__name__)


class ExistingDataError(RuntimeError):
    """The ERP already holds data and overwriting it was not requested."""


def seed(
    conn: psycopg.Connection, config: MarketConfig, seed_value: int, force: bool
) -> dict[str, int]:
    """Writes the reference data; refuses to touch a non-empty ERP unless `force` is set.

    With `force`, every ERP table (transactions included) is emptied first, because
    transactions reference the reference data being replaced.
    """
    data = generate_reference_data(config, seed_value)
    with conn.transaction():
        populated = [t for t in db.ERP_TABLES if db.table_has_rows(conn, t)]
        if populated and not force:
            raise ExistingDataError(
                f"the ERP already contains data ({', '.join(populated)}); use --force to replace it"
            )
        if populated:
            db.truncate(conn, db.ERP_TABLES)
            log(logger, "erp emptied", tables=populated)
        counts = {}
        for table in LOAD_ORDER:
            counts[table] = db.copy_rows_with_ids(conn, table, COLUMNS[table], data.tables[table])
    log(logger, "reference data loaded", seed=seed_value, **counts)
    return counts
