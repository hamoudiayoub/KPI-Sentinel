"""Database access: connection, bulk loading with COPY, and content fingerprints."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import psycopg
from psycopg import sql

from sentinel_gen.settings import Settings

ERP_TABLES = (
    "regions", "cities", "warehouses", "sales_reps", "customers", "brands", "categories",
    "products", "price_changes", "promotions", "orders", "order_lines", "deliveries",
    "returns", "inventory",
)  # fmt: skip

# Surrogate keys assigned by the database during bulk loads of transactions; fingerprints
# ignore them and compare the business content only.
DATABASE_ASSIGNED_IDS = {"order_lines", "deliveries", "returns"}
AUDIT_COLUMNS = {"created_at", "updated_at"}


def connect(settings: Settings) -> psycopg.Connection:
    """Autocommit connection: each `with conn.transaction()` block is its own transaction.

    Without autocommit, psycopg opens an implicit transaction and nested blocks become
    savepoints, so nothing would be committed before the connection closes.
    """
    return psycopg.connect(
        settings.conninfo(), password=settings.db_password.get_secret_value(), autocommit=True
    )


def copy_rows(
    conn: psycopg.Connection, table: str, columns: Sequence[str], rows: Iterable[Sequence[object]]
) -> int:
    """Streams rows into erp.<table> with COPY; returns the number of rows written."""
    statement = sql.SQL("COPY erp.{} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    count = 0
    with conn.cursor() as cur, cur.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def copy_rows_with_ids(
    conn: psycopg.Connection, table: str, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> int:
    """COPY for tables whose id is GENERATED ALWAYS, keeping the ids chosen by the generator.

    COPY cannot override an identity column, so rows go through a temporary table, then
    INSERT ... OVERRIDING SYSTEM VALUE. The identity sequence is moved past the loaded ids.
    """
    temporary = sql.Identifier(f"load_{table}")
    column_list = sql.SQL(", ").join(map(sql.Identifier, columns))
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "CREATE TEMPORARY TABLE {} (LIKE erp.{} INCLUDING DEFAULTS) ON COMMIT DROP"
            ).format(temporary, sql.Identifier(table))
        )
        with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(temporary, column_list)) as copy:
            for row in rows:
                copy.write_row(row)
        cur.execute(
            sql.SQL(
                "INSERT INTO erp.{} ({}) OVERRIDING SYSTEM VALUE SELECT {} FROM {} ORDER BY 1"
            ).format(sql.Identifier(table), column_list, column_list, temporary)
        )
        cur.execute(sql.SQL("DROP TABLE {}").format(temporary))
        if "id" in columns:
            cur.execute(
                sql.SQL(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                    "(SELECT coalesce(max(id), 0) + 1 FROM erp.{}), false)"
                ).format(sql.Identifier(table)),
                (f"erp.{table}",),
            )
    return len(rows)


def table_has_rows(conn: psycopg.Connection, table: str) -> bool:
    query = sql.SQL("SELECT EXISTS (SELECT 1 FROM erp.{})").format(sql.Identifier(table))
    return bool(conn.execute(query).fetchone()[0])


def truncate(conn: psycopg.Connection, tables: Sequence[str]) -> None:
    conn.execute(
        sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(sql.Identifier("erp", t) for t in tables)
        )
    )


def fingerprint(conn: psycopg.Connection, table: str) -> str:
    """SHA-256 of the business content of a table, independent of row order.

    Audit timestamps and database-assigned surrogate keys are excluded, so two loads of
    the same data produce the same fingerprint.
    """
    excluded = AUDIT_COLUMNS | ({"id"} if table in DATABASE_ASSIGNED_IDS else set())
    columns = [
        name
        for (name,) in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'erp' AND table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        if name not in excluded
    ]
    query = sql.SQL(
        "SELECT encode(sha256(convert_to(coalesce("
        "string_agg(r::text, E'\\n' ORDER BY r::text), ''), 'UTF8')), 'hex') "
        "FROM (SELECT {} FROM erp.{}) r"
    ).format(sql.SQL(", ").join(map(sql.Identifier, columns)), sql.Identifier(table))
    return str(conn.execute(query).fetchone()[0])
