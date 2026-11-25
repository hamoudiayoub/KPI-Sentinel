"""The reference data seen by the demand model, as numpy arrays.

Hidden traits that the ERP does not store (size of a point of sale, popularity of a product)
are derived from the seed, so the backfill and the live stream agree on them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import psycopg

from sentinel_gen.config import CHANNELS, MarketConfig
from sentinel_gen.reference import COLUMNS, ReferenceData


@dataclass(frozen=True)
class Market:
    customer_ids: np.ndarray  # (C,) int
    customer_channel: np.ndarray  # (C,) index into CHANNELS
    customer_warehouse: np.ndarray  # (C,) warehouse id
    customer_rep: np.ndarray  # (C,) sales rep id, 0 when unassigned
    customer_lead_days: np.ndarray  # (C,) delivery lead time in days
    customer_size: np.ndarray  # (C,) relative size, mean 1
    product_ids: np.ndarray  # (P,) int
    product_category: np.ndarray  # (P,) index into config.categories
    product_price_cents: np.ndarray  # (P,) list price when loaded
    popularity: np.ndarray  # (P,) selection weight, sums to 1 within each category

    @property
    def customers(self) -> int:
        return len(self.customer_ids)

    @property
    def products(self) -> int:
        return len(self.product_ids)


def build_market(
    config: MarketConfig,
    seed: int,
    customers: list[tuple[int, str, int, int | None, int]],
    products: list[tuple[int, int, int]],
    city_extra_lead: dict[int, int],
    warehouse_lead: dict[int, int],
    customer_city: list[int],
) -> Market:
    """Builds the market arrays.

    customers: (id, channel, warehouse_id, sales_rep_id, city_id) rows;
    products: (id, category_id, price_cents) rows.
    """
    channel_index = {channel: i for i, channel in enumerate(CHANNELS)}
    sigma = config.demand.customer_size_sigma
    size_rng = np.random.default_rng([seed, 101])
    sizes = size_rng.lognormal(-(sigma**2) / 2, sigma, len(customers))

    category = np.array([p[1] - 1 for p in products])
    popularity = np.zeros(len(products))
    popularity_rng = np.random.default_rng([seed, 102])
    for k in range(len(config.categories)):
        members = np.flatnonzero(category == k)
        ranks = popularity_rng.permutation(len(members)) + 1
        weights = 1.0 / ranks**config.demand.popularity_exponent
        popularity[members] = weights / weights.sum()

    return Market(
        customer_ids=np.array([c[0] for c in customers]),
        customer_channel=np.array([channel_index[c[1]] for c in customers]),
        customer_warehouse=np.array([c[2] for c in customers]),
        customer_rep=np.array([c[3] or 0 for c in customers]),
        customer_lead_days=np.array(
            [
                warehouse_lead[c[2]] + city_extra_lead[city]
                for c, city in zip(customers, customer_city, strict=True)
            ]
        ),
        customer_size=sizes,
        product_ids=np.array([p[0] for p in products]),
        product_category=category,
        product_price_cents=np.array([p[2] for p in products], dtype=np.int64),
        popularity=popularity,
    )


def _lead_tables(
    config: MarketConfig, cities: list[tuple[int, int]]
) -> tuple[dict[int, int], dict[int, int]]:
    """cities: (city_id, region_id) -> extra lead days per city, lead days per warehouse id."""
    extra_by_region = {i: r.extra_lead_days for i, r in enumerate(config.regions, 1)}
    city_extra = {city_id: extra_by_region[region_id] for city_id, region_id in cities}
    warehouse_lead = {i: w.lead_days for i, w in enumerate(config.warehouses, 1)}
    return city_extra, warehouse_lead


def market_from_reference(config: MarketConfig, data: ReferenceData, seed: int) -> Market:
    """Builds the market from generated reference data, without a database (tests)."""

    def col(table: str, name: str) -> list:
        index = COLUMNS[table].index(name)
        return [row[index] for row in data.tables[table]]

    city_extra, warehouse_lead = _lead_tables(
        config, list(zip(col("cities", "id"), col("cities", "region_id"), strict=True))
    )
    customers = list(
        zip(
            col("customers", "id"),
            col("customers", "channel"),
            col("customers", "warehouse_id"),
            col("customers", "sales_rep_id"),
            col("customers", "city_id"),
            strict=True,
        )
    )
    products = [
        (pid, cat, round(float(price) * 100))
        for pid, cat, price in zip(
            col("products", "id"),
            col("products", "category_id"),
            col("products", "list_price"),
            strict=True,
        )
    ]
    return build_market(
        config, seed, customers, products, city_extra, warehouse_lead, [c[4] for c in customers]
    )


def load_market(conn: psycopg.Connection, config: MarketConfig, seed: int) -> Market:
    cities = conn.execute("SELECT id, region_id FROM erp.cities ORDER BY id").fetchall()
    city_extra, warehouse_lead = _lead_tables(config, cities)
    customers = conn.execute(
        "SELECT id, channel, warehouse_id, sales_rep_id, city_id FROM erp.customers "
        "WHERE closed_on IS NULL ORDER BY id"
    ).fetchall()
    products = conn.execute(
        "SELECT id, category_id, (list_price * 100)::bigint FROM erp.products "
        "WHERE is_active ORDER BY id"
    ).fetchall()
    if not customers or not products:
        raise RuntimeError("the ERP has no reference data: run `sentinel-gen seed` first")
    return build_market(
        config, seed, customers, products, city_extra, warehouse_lead, [c[4] for c in customers]
    )
