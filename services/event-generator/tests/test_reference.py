"""Unit tests of the reference data generation (pure, no database, no network)."""

from collections import Counter

import pytest

from sentinel_gen.config import CHANNELS
from sentinel_gen.reference import COLUMNS, allocate, generate_reference_data


@pytest.fixture(scope="module")
def data(config):
    return generate_reference_data(config, seed=42)


def column(data, table, name):
    index = COLUMNS[table].index(name)
    return [row[index] for row in data.tables[table]]


def test_allocate_preserves_the_total_and_the_proportions():
    assert allocate(10, [0.7, 0.1, 0.15, 0.05]) == [7, 1, 2, 0]
    assert sum(allocate(2000, [0.7, 0.1, 0.15, 0.05])) == 2000
    assert sum(allocate(37, [3, 1, 1])) == 37


def test_the_same_seed_gives_the_same_data(config, data):
    assert generate_reference_data(config, seed=42).tables == data.tables


def test_another_seed_gives_other_data(config, data):
    assert generate_reference_data(config, seed=7).tables["customers"] != data.tables["customers"]


def test_volumes_match_the_configuration(config, data):
    assert data.count("regions") == 12
    assert 28 <= data.count("cities") <= 35
    assert data.count("warehouses") == 5
    assert data.count("sales_reps") == config.sales_reps
    assert data.count("customers") == config.customers
    assert data.count("categories") == 8
    assert data.count("brands") == 15
    assert data.count("products") == config.products
    assert data.count("inventory") == 5 * config.products


def test_channel_split_matches_the_configuration_within_two_points(config, data):
    counts = Counter(column(data, "customers", "channel"))
    for channel in CHANNELS:
        share = counts[channel] / config.customers
        assert abs(share - config.channels[channel].share) <= 0.02


def test_ids_are_one_to_n_in_order(data):
    for table, columns in COLUMNS.items():
        if columns[0] == "id":
            assert column(data, table, "id") == list(range(1, data.count(table) + 1))


@pytest.mark.parametrize(
    ("table", "column_name", "target"),
    [
        ("cities", "region_id", "regions"),
        ("warehouses", "city_id", "cities"),
        ("sales_reps", "warehouse_id", "warehouses"),
        ("customers", "city_id", "cities"),
        ("customers", "sales_rep_id", "sales_reps"),
        ("customers", "warehouse_id", "warehouses"),
        ("products", "brand_id", "brands"),
        ("products", "category_id", "categories"),
        ("inventory", "warehouse_id", "warehouses"),
        ("inventory", "product_id", "products"),
    ],
)
def test_foreign_keys_point_to_existing_rows(data, table, column_name, target):
    known = set(column(data, target, "id"))
    assert set(column(data, table, column_name)) <= known


def test_customers_are_served_by_the_warehouse_of_their_region(config, data):
    region_of_city = dict(
        zip(column(data, "cities", "id"), column(data, "cities", "region_id"), strict=True)
    )
    warehouse_ids = {w.code: i for i, w in enumerate(config.warehouses, 1)}
    expected = {i: warehouse_ids[r.warehouse] for i, r in enumerate(config.regions, 1)}
    for city_id, warehouse_id in zip(
        column(data, "customers", "city_id"), column(data, "customers", "warehouse_id"), strict=True
    ):
        assert warehouse_id == expected[region_of_city[city_id]]


def test_each_customer_rep_works_at_the_customer_warehouse(data):
    rep_warehouse = dict(
        zip(
            column(data, "sales_reps", "id"),
            column(data, "sales_reps", "warehouse_id"),
            strict=True,
        )
    )
    for rep_id, warehouse_id in zip(
        column(data, "customers", "sales_rep_id"),
        column(data, "customers", "warehouse_id"),
        strict=True,
    ):
        assert rep_warehouse[rep_id] == warehouse_id


def test_prices_are_within_their_category_range(config, data):
    ranges = {i: c.price for i, c in enumerate(config.categories, 1)}
    for category_id, price in zip(
        column(data, "products", "category_id"), column(data, "products", "list_price"), strict=True
    ):
        low, high = ranges[category_id]
        assert low <= float(price) <= high


def test_every_category_has_products_of_its_own_brands(config, data):
    brands_of = {i: set(b.categories) for i, b in enumerate(config.brands, 1)}
    keys = {i: c.key for i, c in enumerate(config.categories, 1)}
    for brand_id, category_id in zip(
        column(data, "products", "brand_id"), column(data, "products", "category_id"), strict=True
    ):
        assert keys[category_id] in brands_of[brand_id]
    assert set(column(data, "products", "category_id")) == set(keys)
