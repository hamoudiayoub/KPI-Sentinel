"""Checks the ERP schema applied by Flyway on the running `core` profile.

Statements that write data run inside BEGIN ... ROLLBACK, so the tests leave no trace.
"""

import pytest

pytestmark = pytest.mark.integration

ERP_TABLES = {
    "regions", "cities", "warehouses", "sales_reps", "customers",
    "brands", "categories", "products", "price_changes", "promotions",
    "orders", "order_lines", "deliveries", "returns", "inventory",
}  # fmt: skip


def erp(psql, sql):
    return psql("postgres-source", sql, database="atlas")


def rows(output):
    return set(output.splitlines()) if output else set()


def test_migrations_are_all_applied_successfully(psql):
    failed = erp(psql, "SELECT count(*) FROM flyway.flyway_schema_history WHERE NOT success;")
    applied = erp(
        psql, "SELECT count(*) FROM flyway.flyway_schema_history WHERE version IS NOT NULL;"
    )
    assert failed == "0"
    assert int(applied) >= 4


def test_erp_schema_has_exactly_the_fifteen_tables(psql):
    tables = erp(psql, "SELECT tablename FROM pg_tables WHERE schemaname = 'erp';")
    assert rows(tables) == ERP_TABLES


def test_publication_covers_every_erp_table(psql):
    published = erp(
        psql,
        "SELECT tablename FROM pg_publication_tables "
        "WHERE pubname = 'sentinel_pub' AND schemaname = 'erp';",
    )
    assert rows(published) == ERP_TABLES


def test_orders_and_inventory_keep_a_full_before_image(psql):
    identities = erp(
        psql,
        "SELECT c.relname || ':' || c.relreplident::text FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'erp' AND c.relkind = 'r';",
    )
    by_table = dict(line.split(":") for line in identities.splitlines())
    assert by_table.pop("orders") == "f"
    assert by_table.pop("inventory") == "f"
    assert set(by_table.values()) == {"d"}


def test_every_table_has_the_updated_at_trigger(psql):
    triggered = erp(
        psql,
        "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'erp' AND t.tgname = 'set_updated_at';",
    )
    assert rows(triggered) == ERP_TABLES


def test_update_refreshes_updated_at(psql):
    result = erp(
        psql,
        [
            "BEGIN;",
            "INSERT INTO erp.regions (code, name, created_at, updated_at) "
            "VALUES ('TST', 'Test region', '2000-01-01', '2000-01-01');",
            "UPDATE erp.regions SET name = 'Renamed region' WHERE code = 'TST';",
            "SELECT updated_at > created_at FROM erp.regions WHERE code = 'TST';",
            "ROLLBACK;",
        ],
    )
    assert result == "t"


def test_debezium_role_can_replicate_and_read(psql, env):
    assert erp(psql, "SELECT rolreplication FROM pg_roles WHERE rolname = 'debezium';") == "t"
    count = psql(
        "postgres-source",
        "SELECT count(*) FROM erp.regions;",
        user="debezium",
        database="atlas",
        password=env["DEBEZIUM_DB_PASSWORD"],
    )
    assert count.isdigit()


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO erp.regions (code, name) VALUES ('X', 'X');",
        "UPDATE erp.regions SET name = name;",
        "DELETE FROM erp.regions;",
    ],
)
def test_debezium_role_cannot_write(psql, statement):
    with pytest.raises(RuntimeError, match="permission denied"):
        erp(psql, ["SET ROLE debezium;", statement])


ORDER_FIXTURE = [
    "BEGIN;",
    "INSERT INTO erp.regions (code, name) VALUES ('TST', 'Test region');",
    "INSERT INTO erp.cities (region_id, name) "
    "SELECT id, 'Test city' FROM erp.regions WHERE code = 'TST';",
    "INSERT INTO erp.warehouses (code, name, city_id) "
    "SELECT 'TST', 'Test warehouse', id FROM erp.cities WHERE name = 'Test city';",
    "INSERT INTO erp.customers (code, name, channel, city_id, warehouse_id, opened_on) "
    "SELECT 'TST', 'Test customer', 'TRADITIONAL', w.city_id, w.id, '2025-01-01' "
    "FROM erp.warehouses w WHERE w.code = 'TST';",
    "INSERT INTO erp.brands (name) VALUES ('Test brand');",
    "INSERT INTO erp.categories (name) VALUES ('Test category');",
    "INSERT INTO erp.products (sku, name, brand_id, category_id, pack_size, list_price) "
    "SELECT 'TST-1', 'Test product', b.id, c.id, '1 L', 10 "
    "FROM erp.brands b, erp.categories c WHERE b.name = 'Test brand' AND c.name = 'Test category';",
    "INSERT INTO erp.orders (id, customer_id, warehouse_id, channel, placed_at) "
    "SELECT '00000000-0000-0000-0000-000000000001', c.id, c.warehouse_id, c.channel, now() "
    "FROM erp.customers c WHERE c.code = 'TST';",
]


def insert_order_line(quantity, unit_price, gross_amount, discount_amount):
    return (
        "INSERT INTO erp.order_lines "
        "(order_id, line_number, product_id, quantity, unit_price, gross_amount, discount_amount) "
        f"SELECT '00000000-0000-0000-0000-000000000001', 1, id, {quantity}, {unit_price}, "
        f"{gross_amount}, {discount_amount} FROM erp.products WHERE sku = 'TST-1';"
    )


def test_a_valid_order_line_is_accepted(psql):
    result = erp(
        psql,
        [
            *ORDER_FIXTURE,
            insert_order_line(3, 10, 30, 5),
            "SELECT count(*) FROM erp.order_lines "
            "WHERE order_id = '00000000-0000-0000-0000-000000000001';",
            "ROLLBACK;",
        ],
    )
    assert result == "1"


@pytest.mark.parametrize(
    ("line", "violated_check"),
    [
        (insert_order_line(0, 10, 0, 0), "order_lines_quantity_check"),
        (insert_order_line(2, 10, 30, 0), "order_lines_gross_equals_quantity_times_price_check"),
        (insert_order_line(1, 10, 10, 11), "order_lines_discount_within_gross_check"),
    ],
    ids=["zero-quantity", "wrong-gross-amount", "discount-above-gross"],
)
def test_an_invalid_order_line_is_rejected(psql, line, violated_check):
    with pytest.raises(RuntimeError, match=violated_check):
        erp(psql, [*ORDER_FIXTURE, line, "ROLLBACK;"])


def test_a_negative_list_price_is_rejected(psql):
    with pytest.raises(RuntimeError, match="products_list_price_check"):
        erp(
            psql,
            [
                *ORDER_FIXTURE,
                "UPDATE erp.products SET list_price = -1 WHERE sku = 'TST-1';",
                "ROLLBACK;",
            ],
        )


def test_table_level_checks_have_explicit_names(psql):
    # PostgreSQL names an unnamed table-level check <table>_check, <table>_check1, …
    generated = erp(
        psql,
        "SELECT c.conname FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid "
        "WHERE c.connamespace = 'erp'::regnamespace AND c.contype = 'c' "
        "AND c.conname ~ ('^' || r.relname || '_check[0-9]*$');",
    )
    assert generated == ""
