"""Backfill of the order history: prices, promotions, orders and their lifecycle.

Generation (plan_prices, plan_promotions, generate_history) is pure and deterministic:
each day draws from its own generator, seeded by (seed, day), so the result does not depend
on how the work is batched. `backfill` loads it with COPY, one transaction per month.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import numpy as np
import psycopg

from sentinel_gen import db
from sentinel_gen.calendar import Calendar
from sentinel_gen.config import CHANNELS, MarketConfig
from sentinel_gen.demand import (
    NONE,
    RETURN_REASONS,
    DemandModel,
    Lines,
    Promotions,
    Schedule,
    cents,
    days,
    epoch,
    to_date,
    to_iso,
)
from sentinel_gen.logs import log
from sentinel_gen.market import Market, load_market

logger = logging.getLogger(__name__)

HISTORY_TABLES = ("price_changes", "promotions", "orders", "order_lines", "deliveries", "returns")

ORDER_COLUMNS = (
    "id", "customer_id", "sales_rep_id", "warehouse_id", "channel", "status",
    "placed_at", "confirmed_at", "shipped_at", "delivered_at", "cancelled_at",
)  # fmt: skip
LINE_COLUMNS = (
    "order_id", "line_number", "product_id", "promotion_id", "quantity", "unit_price",
    "gross_amount", "discount_amount",
)  # fmt: skip
DELIVERY_COLUMNS = (
    "order_id", "warehouse_id", "promised_on", "status", "shipped_at", "delivered_at",
    "delivered_units",
)  # fmt: skip
RETURN_COLUMNS = ("order_id", "product_id", "quantity", "amount", "reason", "returned_at")
PRICE_COLUMNS = ("id", "product_id", "effective_from", "list_price")
PROMOTION_COLUMNS = ("id", "product_id", "channel", "starts_on", "ends_on", "discount_pct")


class ExistingHistoryError(RuntimeError):
    """The ERP already holds transactions and replacing them was not requested."""


def months_before(end: date, months: int) -> date:
    month_index = end.year * 12 + end.month - 1 - months
    return date(month_index // 12, month_index % 12 + 1, 1)


@dataclass(frozen=True)
class PricePlan:
    rows: list[tuple[int, int, str, str]]  # price_changes rows
    changes: dict[date, list[tuple[int, int]]]  # day -> [(product index, new price in cents)]
    final_cents: np.ndarray


def plan_prices(
    config: MarketConfig, market: Market, start: date, end: date, seed: int
) -> PricePlan:
    """Opening price of every product at `start`, then a few increases, mostly in January."""
    rng = np.random.default_rng([seed, 3])
    current = market.product_price_cents.copy()
    events: list[tuple[date, int, int]] = []
    span = (end - start).days
    januaries = [d for d in days(start, end) if d.month == 1 and 2 <= d.day <= 15]
    for index in range(market.products):
        for _ in range(int(rng.poisson(config.demand.history.price_increases_per_product))):
            if januaries and rng.random() < 0.5:
                day = januaries[int(rng.integers(len(januaries)))]
            else:
                day = start + timedelta(days=int(rng.integers(1, span)))
            increase = 1 + float(rng.uniform(0.02, 0.08))
            events.append((day, index, increase))
    events.sort(key=lambda e: (e[0], e[1]))

    rows = [
        (i + 1, int(market.product_ids[i]), start.isoformat(), cents(current[i : i + 1])[0])
        for i in range(market.products)
    ]
    changes: dict[date, list[tuple[int, int]]] = {}
    seen: set[tuple[date, int]] = set()
    for day, index, increase in events:
        if (day, index) in seen:  # one change per product and day
            continue
        seen.add((day, index))
        current[index] = int(round(current[index] * increase / 5) * 5)  # multiples of 0.05 MAD
        changes.setdefault(day, []).append((index, int(current[index])))
        rows.append(
            (
                len(rows) + 1,
                int(market.product_ids[index]),
                day.isoformat(),
                cents(current[index : index + 1])[0],
            )
        )
    return PricePlan(rows=rows, changes=changes, final_cents=current)


@dataclass(frozen=True)
class PromotionPlan:
    rows: list[tuple[int, int, str | None, str, str, str]]
    by_day: dict[date, Promotions] = field(default_factory=dict)


def plan_promotions(
    config: MarketConfig, market: Market, start: date, end: date, seed: int
) -> PromotionPlan:
    """A few promotions a month on popular products, sometimes limited to one channel."""
    rng = np.random.default_rng([seed, 4])
    months = (end.year - start.year) * 12 + end.month - start.month
    count = round(months * config.demand.history.promotions_per_month)
    popularity = market.popularity / market.popularity.sum()
    rows = []
    for promotion_id in range(1, count + 1):
        product = int(rng.choice(market.products, p=popularity))
        starts = start + timedelta(days=int(rng.integers(0, (end - start).days - 7)))
        ends = min(starts + timedelta(days=int(rng.integers(7, 22))), end - timedelta(days=1))
        channel = str(rng.choice(CHANNELS)) if rng.random() < 0.3 else None
        pct = float(rng.choice([5, 10, 15, 20]))
        rows.append(
            (
                promotion_id,
                int(market.product_ids[product]),
                channel,
                starts.isoformat(),
                ends.isoformat(),
                f"{pct:.2f}",
            )
        )
    product_index = {int(pid): i for i, pid in enumerate(market.product_ids)}
    by_day: dict[date, Promotions] = {}
    for day in days(start, end):
        active = Promotions.none(market.products)
        for promotion_id, product_id, channel, starts, ends, pct in rows:
            if starts <= day.isoformat() <= ends:
                channels = range(len(CHANNELS)) if channel is None else [CHANNELS.index(channel)]
                index = product_index[product_id]
                for c in channels:
                    if float(pct) > active.pct[c, index]:
                        active.pct[c, index] = float(pct)
                        active.promotion_id[c, index] = promotion_id
        by_day[day] = active
    return PromotionPlan(rows=rows, by_day=by_day)


@dataclass
class Batch:
    """Rows of one month, written in one transaction."""

    month: date
    orders: list[tuple] = field(default_factory=list)
    lines: list[tuple] = field(default_factory=list)
    deliveries: list[tuple] = field(default_factory=list)
    returns: list[tuple] = field(default_factory=list)


def order_status(schedule_at: dict[str, np.ndarray], cutoff: int) -> np.ndarray:
    """Status of each order at `cutoff`, from its lifecycle timestamps."""

    def reached(name: str) -> np.ndarray:
        ts = schedule_at[name]
        return (ts != NONE) & (ts < cutoff)

    status = np.full(len(schedule_at["placed_at"]), "PLACED", dtype=object)
    status[reached("confirmed_at")] = "CONFIRMED"
    status[reached("shipped_at")] = "SHIPPED"
    status[reached("delivered_at")] = "DELIVERED"
    status[reached("cancelled_at")] = "CANCELLED"
    return status


def generate_history(
    config: MarketConfig,
    calendar: Calendar,
    market: Market,
    start: date,
    end: date,
    seed: int,
    scale: float,
    prices: PricePlan,
    promotions: PromotionPlan,
) -> Iterator[Batch]:
    model = DemandModel(config, calendar, market)
    cutoff = epoch(end)
    current_prices = market.product_price_cents.copy()
    batch: Batch | None = None
    for day in days(start, end):
        for index, price in prices.changes.get(day, []):
            current_prices[index] = price
        month = day.replace(day=1)
        if batch is None or batch.month != month:
            if batch is not None:
                yield batch
            batch = Batch(month=month)
        rng = np.random.default_rng([seed, 2, day.toordinal()])
        customers = model.daily_orders(rng, day, scale)
        if not len(customers):
            continue
        placed = model.place_times(rng, day, len(customers))
        rng.shuffle(customers)  # orders are sorted by time; customers in random order
        channels = market.customer_channel[customers]
        lines = model.basket(rng, day, channels, current_prices, promotions.by_day[day])
        schedule = model.lifecycle(rng, placed, market.customer_lead_days[customers])
        order_ids = [str(uuid.UUID(bytes=rng.bytes(16), version=4)) for _ in customers]
        _append_day(
            batch,
            model,
            rng,
            market,
            customers,
            channels,
            placed,
            schedule,
            lines,
            order_ids,
            cutoff,
        )
    if batch is not None:
        yield batch


def _visible(ts: np.ndarray, cutoff: int) -> np.ndarray:
    """Hides lifecycle steps that happen after the end of the history."""
    return np.where((ts != NONE) & (ts < cutoff), ts, NONE)


def _append_day(
    batch: Batch,
    model: DemandModel,
    rng: np.random.Generator,
    market: Market,
    customers: np.ndarray,
    channels: np.ndarray,
    placed: np.ndarray,
    schedule: Schedule,
    lines: Lines,
    order_ids: list[str],
    cutoff: int,
) -> None:
    at = {
        "placed_at": placed,
        "confirmed_at": _visible(schedule.confirmed_at, cutoff),
        "shipped_at": _visible(schedule.shipped_at, cutoff),
        "delivered_at": _visible(schedule.delivered_at, cutoff),
        "cancelled_at": _visible(schedule.cancelled_at, cutoff),
    }
    status = order_status(at, cutoff)
    iso = {name: to_iso(values) for name, values in at.items()}
    warehouse = market.customer_warehouse[customers]
    for i, order_id in enumerate(order_ids):
        rep = int(market.customer_rep[customers[i]])
        batch.orders.append(
            (
                order_id, int(market.customer_ids[customers[i]]), rep or None, int(warehouse[i]),
                CHANNELS[channels[i]], status[i], iso["placed_at"][i], iso["confirmed_at"][i],
                iso["shipped_at"][i], iso["delivered_at"][i], iso["cancelled_at"][i],
            )
        )  # fmt: skip

    unit_price, gross, discount = (
        cents(lines.unit_price_cents), cents(lines.gross_cents), cents(lines.discount_cents),
    )  # fmt: skip
    product_ids = market.product_ids[lines.product]
    for j in range(len(lines.order)):
        promotion = int(lines.promotion_id[j])
        batch.lines.append(
            (
                order_ids[lines.order[j]], int(lines.line_number[j]), int(product_ids[j]),
                promotion or None, int(lines.quantity[j]), unit_price[j], gross[j], discount[j],
            )
        )  # fmt: skip

    # A delivery exists once an order is confirmed; it fails if the order is cancelled later.
    units = np.bincount(lines.order, weights=lines.quantity, minlength=len(customers))
    delivered_units = np.floor(units * schedule.delivered_fraction).astype(np.int64)
    promised = to_date(schedule.promised_on)
    confirmed = at["confirmed_at"] != NONE
    for i, order_id in enumerate(order_ids):
        if not confirmed[i]:
            continue
        delivery_status = {
            "CONFIRMED": "SCHEDULED", "SHIPPED": "IN_TRANSIT", "CANCELLED": "FAILED",
        }.get(status[i], "DELIVERED")  # fmt: skip
        batch.deliveries.append(
            (
                order_id, int(warehouse[i]), promised[i], delivery_status, iso["shipped_at"][i],
                iso["delivered_at"][i], int(delivered_units[i]) if status[i] == "DELIVERED" else 0,
            )
        )  # fmt: skip

    line_index, quantity, returned_at, reason = model.returns(rng, lines, at["delivered_at"])
    keep = returned_at < cutoff
    net_unit = (lines.gross_cents - lines.discount_cents) // lines.quantity
    amounts = cents(net_unit[line_index] * quantity)
    returned = to_iso(returned_at)
    for r in np.flatnonzero(keep):
        j = line_index[r]
        batch.returns.append(
            (
                order_ids[lines.order[j]], int(product_ids[j]), int(quantity[r]), amounts[r],
                RETURN_REASONS[reason[r]], returned[r],
            )
        )  # fmt: skip


def backfill(
    conn: psycopg.Connection,
    config: MarketConfig,
    calendar: Calendar,
    seed: int,
    months: int,
    scale: float,
    end: date,
    force: bool,
) -> dict[str, int]:
    start = months_before(end, months)
    if not calendar.covers(start, end):
        raise ValueError(f"the calendar does not cover {start} to {end}")
    with conn.transaction():
        populated = [t for t in HISTORY_TABLES if db.table_has_rows(conn, t)]
        # A previous backfill moved products.list_price to its last price change; the
        # opening prices it started from are its earliest price changes.
        opening_prices = dict(
            conn.execute(
                "SELECT DISTINCT ON (product_id) product_id, (list_price * 100)::bigint "
                "FROM erp.price_changes ORDER BY product_id, effective_from"
            ).fetchall()
        )
        if populated and not force:
            raise ExistingHistoryError(
                f"the ERP already contains transactions ({', '.join(populated)}); "
                "use --force to replace them"
            )
        if populated:
            db.truncate(conn, HISTORY_TABLES)
            log(logger, "history emptied", tables=populated)

    began = time.monotonic()
    market = load_market(conn, config, seed)
    if opening_prices:
        market = replace(
            market,
            product_price_cents=np.array(
                [
                    opening_prices.get(int(pid), cents_)
                    for pid, cents_ in zip(
                        market.product_ids, market.product_price_cents, strict=True
                    )
                ],
                dtype=np.int64,
            ),
        )
    prices = plan_prices(config, market, start, end, seed)
    promotions = plan_promotions(config, market, start, end, seed)
    with conn.transaction():
        db.copy_rows_with_ids(conn, "price_changes", PRICE_COLUMNS, prices.rows)
        db.copy_rows_with_ids(conn, "promotions", PROMOTION_COLUMNS, promotions.rows)

    totals = dict.fromkeys(("orders", "order_lines", "deliveries", "returns"), 0)
    for batch in generate_history(
        config, calendar, market, start, end, seed, scale, prices, promotions
    ):
        with conn.transaction():
            totals["orders"] += db.copy_rows(conn, "orders", ORDER_COLUMNS, batch.orders)
            totals["order_lines"] += db.copy_rows(conn, "order_lines", LINE_COLUMNS, batch.lines)
            totals["deliveries"] += db.copy_rows(
                conn, "deliveries", DELIVERY_COLUMNS, batch.deliveries
            )
            totals["returns"] += db.copy_rows(conn, "returns", RETURN_COLUMNS, batch.returns)
        log(
            logger,
            "month loaded",
            month=batch.month.isoformat(),
            orders=len(batch.orders),
            lines=len(batch.lines),
        )

    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "UPDATE erp.products SET list_price = %s WHERE id = %s AND list_price <> %s",
            [
                (price, int(pid), price)
                for pid, price in zip(market.product_ids, cents(prices.final_cents), strict=True)
            ],
        )
    totals["price_changes"] = len(prices.rows)
    totals["promotions"] = len(promotions.rows)
    log(logger, "history loaded", start=start.isoformat(), end=end.isoformat(), seed=seed,
        scale=scale, seconds=round(time.monotonic() - began, 1), **totals)  # fmt: skip
    return totals
