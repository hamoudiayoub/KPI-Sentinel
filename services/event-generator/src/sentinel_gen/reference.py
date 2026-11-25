"""Reference data of the simulated ERP: geography, warehouses, sales reps, customers, catalog.

Generation is pure and deterministic: one seeded random generator, consumed in a fixed order.
Rows carry explicit ids (1..n, in generation order), so foreign keys are known before loading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from sentinel_gen.config import CHANNELS, MarketConfig

Row = tuple[object, ...]

# Columns loaded for each table, in row order. Audit columns are left to their defaults.
COLUMNS: dict[str, tuple[str, ...]] = {
    "regions": ("id", "code", "name"),
    "cities": ("id", "region_id", "name"),
    "warehouses": ("id", "code", "name", "city_id"),
    "sales_reps": ("id", "code", "full_name", "warehouse_id", "hired_on", "left_on"),
    "customers": (
        "id", "code", "name", "channel", "city_id", "sales_rep_id", "warehouse_id",
        "opened_on", "closed_on",
    ),
    "brands": ("id", "name"),
    "categories": ("id", "name"),
    "products": (
        "id", "sku", "name", "brand_id", "category_id", "pack_size", "list_price", "is_active",
    ),
    "inventory": ("warehouse_id", "product_id", "quantity_on_hand", "reorder_point"),
}  # fmt: skip

# Load order respects foreign keys.
LOAD_ORDER = tuple(COLUMNS)


@dataclass
class ReferenceData:
    tables: dict[str, list[Row]] = field(default_factory=dict)

    def count(self, table: str) -> int:
        return len(self.tables[table])


def allocate(total: int, weights: list[float]) -> list[int]:
    """Splits `total` into integer parts proportional to `weights` (largest remainder)."""
    raw = np.asarray(weights, dtype=float) / float(np.sum(weights)) * total
    counts = np.floor(raw).astype(int)
    remainder = total - int(counts.sum())
    for index in np.argsort(-(raw - counts), kind="stable")[:remainder]:
        counts[index] += 1
    return [int(c) for c in counts]


def random_date(rng: np.random.Generator, start: date, end: date) -> date:
    return start + timedelta(days=int(rng.integers(0, (end - start).days + 1)))


def generate_reference_data(config: MarketConfig, seed: int) -> ReferenceData:
    rng = np.random.default_rng(seed)
    data = ReferenceData()

    # Geography.
    data.tables["regions"] = [(i, r.code, r.name) for i, r in enumerate(config.regions, 1)]
    cities: list[Row] = []
    city_region: list[int] = []
    city_weight: list[float] = []
    for region_id, region in enumerate(config.regions, 1):
        for name, weight in region.cities.items():
            cities.append((len(cities) + 1, region_id, name))
            city_region.append(region_id - 1)
            city_weight.append(weight)
    data.tables["cities"] = cities
    city_id_by_name = {row[2]: row[0] for row in cities}

    warehouse_id_by_code = {w.code: i for i, w in enumerate(config.warehouses, 1)}
    data.tables["warehouses"] = [
        (i, w.code, w.name, city_id_by_name[w.city]) for i, w in enumerate(config.warehouses, 1)
    ]
    city_warehouse = [
        warehouse_id_by_code[config.regions[region].warehouse] for region in city_region
    ]

    # Customers: exact channel split, then a city drawn by channel-specific weights.
    channel_counts = allocate(config.customers, [config.channels[c].share for c in CHANNELS])
    channels = np.repeat(np.array(CHANNELS), channel_counts)
    rng.shuffle(channels)
    weights = np.asarray(city_weight)
    customer_city = np.empty(config.customers, dtype=int)
    for channel in CHANNELS:
        mask = channels == channel
        p = weights ** config.channels[channel].city_weight_exponent
        customer_city[mask] = rng.choice(len(cities), size=int(mask.sum()), p=p / p.sum())
    customer_warehouse = np.asarray(city_warehouse)[customer_city]

    # Sales reps: split across warehouses by their number of customers, at least one each.
    customers_per_warehouse = [
        int((customer_warehouse == wid).sum()) for wid in range(1, len(config.warehouses) + 1)
    ]
    rep_counts = [
        1 + c for c in allocate(config.sales_reps - len(config.warehouses), customers_per_warehouse)
    ]
    reps: list[Row] = []
    reps_by_warehouse: dict[int, list[int]] = {}
    for warehouse_id, count in enumerate(rep_counts, 1):
        for _ in range(count):
            rep_id = len(reps) + 1
            name = f"{rng.choice(config.names.first_names)} {rng.choice(config.names.last_names)}"
            hired = random_date(rng, date(2012, 1, 1), date(2024, 12, 31))
            reps.append((rep_id, f"REP-{rep_id:03d}", name, warehouse_id, hired, None))
            reps_by_warehouse.setdefault(warehouse_id, []).append(rep_id)
    data.tables["sales_reps"] = reps

    customers: list[Row] = []
    for index in range(config.customers):
        customer_id = index + 1
        channel = str(channels[index])
        warehouse_id = int(customer_warehouse[index])
        prefix = rng.choice(config.names.shop_prefixes[channel])
        word = rng.choice(config.names.shop_words)
        customers.append(
            (
                customer_id,
                f"CUS-{customer_id:05d}",
                f"{prefix} {word}",
                channel,
                int(customer_city[index]) + 1,
                int(rng.choice(reps_by_warehouse[warehouse_id])),
                warehouse_id,
                random_date(rng, date(2005, 1, 1), date(2024, 12, 31)),
                None,
            )
        )
    data.tables["customers"] = customers

    # Catalog.
    data.tables["brands"] = [(i, b.name) for i, b in enumerate(config.brands, 1)]
    data.tables["categories"] = [(i, c.name) for i, c in enumerate(config.categories, 1)]
    brands_by_category = {
        c.key: [i for i, b in enumerate(config.brands, 1) if c.key in b.categories]
        for c in config.categories
    }
    brand_names = {i: b.name for i, b in enumerate(config.brands, 1)}
    products: list[Row] = []
    counts = allocate(config.products, [c.weight for c in config.categories])
    for category_id, (category, count) in enumerate(zip(config.categories, counts, strict=True), 1):
        low, high = category.price
        for _ in range(count):
            product_id = len(products) + 1
            brand_id = int(rng.choice(brands_by_category[category.key]))
            kind = rng.choice(category.types)
            pack = str(rng.choice(category.packs))
            price = round(float(rng.uniform(low, high)) * 20) / 20  # multiples of 0.05 MAD
            products.append(
                (
                    product_id,
                    f"SKU-{product_id:05d}",
                    f"{brand_names[brand_id]} {kind} {pack}",
                    brand_id,
                    category_id,
                    pack,
                    f"{price:.2f}",
                    True,
                )
            )
    data.tables["products"] = products

    # Opening stock of every product in every warehouse.
    data.tables["inventory"] = [
        (warehouse_id, product[0], int(rng.integers(200, 2001)), 150)
        for warehouse_id in range(1, len(config.warehouses) + 1)
        for product in products
    ]
    return data
