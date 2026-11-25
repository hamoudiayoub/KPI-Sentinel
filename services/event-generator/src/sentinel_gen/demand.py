"""Demand model of Atlas Distribution, shared by the history backfill and the live stream.

Everything here is pure: given a random generator, a day and the market, it returns numpy
arrays. Timestamps are integer seconds since the Unix epoch, in UTC. Money is in integer
cents (MAD), so amounts are exact. MODEL.md explains the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np

from sentinel_gen.calendar import Calendar
from sentinel_gen.config import CHANNELS, MarketConfig
from sentinel_gen.market import Market

DAY = 86_400
HOUR = 3_600
NONE = -1  # missing timestamp in timestamp arrays
TREND_ORIGIN = date(2025, 1, 1)
RETURN_REASONS = ("DAMAGED", "EXPIRED", "WRONG_ITEM", "CUSTOMER_REFUSAL", "OTHER")
RETURN_REASON_WEIGHTS = (0.35, 0.25, 0.15, 0.15, 0.10)


def epoch(day: date) -> int:
    """Seconds since the epoch at 00:00 UTC of `day`."""
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


@dataclass(frozen=True)
class Promotions:
    """Promotions in effect on one day, indexed by (channel, product)."""

    pct: np.ndarray  # (len(CHANNELS), P) discount in %, 0 when none
    promotion_id: np.ndarray  # (len(CHANNELS), P) promotion id, 0 when none

    @staticmethod
    def none(products: int) -> Promotions:
        shape = (len(CHANNELS), products)
        return Promotions(np.zeros(shape), np.zeros(shape, dtype=np.int64))


@dataclass(frozen=True)
class Lines:
    """Order lines of a batch of orders; `order` indexes the batch."""

    order: np.ndarray
    line_number: np.ndarray
    product: np.ndarray  # index into the market's products
    quantity: np.ndarray
    unit_price_cents: np.ndarray
    gross_cents: np.ndarray
    discount_cents: np.ndarray
    promotion_id: np.ndarray  # 0 when no promotion applied


@dataclass(frozen=True)
class Schedule:
    """Lifecycle timestamps of a batch of orders (NONE when the step never happens)."""

    confirmed_at: np.ndarray
    shipped_at: np.ndarray
    delivered_at: np.ndarray
    cancelled_at: np.ndarray
    promised_on: np.ndarray  # epoch seconds at 00:00 UTC of the promised date
    delivered_fraction: np.ndarray  # share of the ordered units that is delivered


class DemandModel:
    def __init__(self, config: MarketConfig, calendar: Calendar, market: Market) -> None:
        self.config = config
        self.calendar = calendar
        self.market = market
        demand = config.demand
        profiles = [config.channels[c] for c in CHANNELS]
        self.orders_per_day = np.array([p.orders_per_day for p in profiles])
        self.lines_per_order = np.array([p.lines_per_order for p in profiles])
        self.units_per_line = np.array([p.units_per_line for p in profiles])
        self.weekday = np.array([p.weekday_factors for p in profiles])  # (4, 7)
        weights = np.array([c.weight for c in config.categories])
        self.category_weights = weights / weights.sum()
        keys = [c.key for c in config.categories]
        self.ramadan_uplift = np.array([demand.ramadan.category_uplift.get(k, 0.0) for k in keys])
        self.ramadan_channel = np.array([demand.ramadan.channel_factors[c] for c in CHANNELS])
        self.season_amplitude = np.array(
            [demand.seasonality[k].amplitude if k in demand.seasonality else 0.0 for k in keys]
        )
        self.season_peak = np.array(
            [demand.seasonality[k].peak_day if k in demand.seasonality else 1 for k in keys]
        )
        self.products_by_category = [
            np.flatnonzero(market.product_category == k) for k in range(len(keys))
        ]

    # --- How many orders -------------------------------------------------------------

    def channel_factors(self, day: date) -> np.ndarray:
        """(4,) multiplier of the order rate of each channel on `day`."""
        demand = self.config.demand
        factors = self.weekday[:, day.weekday()].copy()
        factors *= (1 + demand.yearly_trend) ** ((day - TREND_ORIGIN).days / 365.25)
        eid = self.calendar.eid_days.get(day)
        if eid == 1:
            factors *= demand.eid.first_day
        elif eid == 2:
            factors *= demand.eid.following_days
        elif self.calendar.is_holiday(day):
            factors *= demand.public_holiday
        if self.calendar.days_before_eid(day) is not None:
            factors *= demand.eid.week_before
        if self.calendar.is_ramadan(day):
            factors *= self.ramadan_channel
        return factors

    def order_rates(self, day: date) -> np.ndarray:
        """(C,) expected number of orders of each point of sale on `day`."""
        channel = self.market.customer_channel
        return (
            self.orders_per_day[channel]
            * self.market.customer_size
            * self.channel_factors(day)[channel]
        )

    def daily_orders(self, rng: np.random.Generator, day: date, scale: float) -> np.ndarray:
        """Customer index of each order placed on `day` (a market shock makes days vary)."""
        shape = self.config.demand.market_shock_shape
        shock = rng.gamma(shape, 1 / shape)
        counts = rng.poisson(self.order_rates(day) * shock * scale)
        return np.repeat(np.arange(self.market.customers), counts)

    # --- What is ordered ------------------------------------------------------------

    def line_means(self, day: date) -> np.ndarray:
        """(4, K) expected number of lines of each category in an order of each channel."""
        doy = day.timetuple().tm_yday
        season = 1 + self.season_amplitude * np.cos(2 * np.pi * (doy - self.season_peak) / 365.25)
        ramadan = 1 + self.ramadan_uplift if self.calendar.is_ramadan(day) else 1.0
        per_category = self.category_weights * season * ramadan
        return self.lines_per_order[:, None] * per_category[None, :]

    def basket(
        self,
        rng: np.random.Generator,
        day: date,
        channels: np.ndarray,
        prices_cents: np.ndarray,
        promotions: Promotions,
    ) -> Lines:
        """Lines of a batch of orders; `channels` gives the channel index of each order."""
        means = self.line_means(day)
        counts = rng.poisson(means[channels])  # (N, K)
        empty = np.flatnonzero(counts.sum(axis=1) == 0)
        if len(empty):
            counts[empty, rng.choice(counts.shape[1], size=len(empty), p=self.category_weights)] = 1

        uplift = self.config.demand.promotion_uplift
        order_parts: list[np.ndarray] = []
        product_parts: list[np.ndarray] = []
        for channel in range(len(CHANNELS)):
            orders = np.flatnonzero(channels == channel)
            if not len(orders):
                continue
            boost = np.where(promotions.pct[channel] > 0, uplift, 1.0)
            for k, members in enumerate(self.products_by_category):
                per_order = counts[orders, k]
                total = int(per_order.sum())
                if not total:
                    continue
                weights = self.market.popularity[members] * boost[members]
                product_parts.append(rng.choice(members, size=total, p=weights / weights.sum()))
                order_parts.append(np.repeat(orders, per_order))
        order = np.concatenate(order_parts)
        product = np.concatenate(product_parts)
        draws = 1 + rng.poisson(self.units_per_line[channels[order]] - 1)

        # The same product drawn twice in an order becomes one line with both quantities.
        products = self.market.products
        keys, inverse = np.unique(order * products + product, return_inverse=True)
        quantity = np.bincount(inverse, weights=draws).astype(np.int64)
        order, product = keys // products, keys % products
        first_line = np.searchsorted(order, order, side="left")
        line_number = np.arange(len(order)) - first_line + 1

        line_channel = channels[order]
        unit_price = prices_cents[product]
        gross = quantity * unit_price
        promo_pct = promotions.pct[line_channel, product]
        volume_pct = np.zeros(len(order))
        for minimum, pct in self.config.demand.volume_discounts:
            volume_pct = np.where(quantity >= minimum, pct, volume_pct)
        discount = np.minimum(np.floor(gross * (promo_pct + volume_pct) / 100), gross).astype(
            np.int64
        )
        return Lines(
            order=order,
            line_number=line_number,
            product=product,
            quantity=quantity,
            unit_price_cents=unit_price,
            gross_cents=gross,
            discount_cents=discount,
            promotion_id=promotions.promotion_id[line_channel, product],
        )

    # --- When ------------------------------------------------------------------------

    def place_times(self, rng: np.random.Generator, day: date, count: int) -> np.ndarray:
        """UTC timestamps of `count` orders placed on local date `day`.

        Orders come in a morning and an afternoon wave; during Ramadan the afternoon wave
        moves to the evening, after the fast is broken.
        """
        if self.calendar.is_ramadan(day):
            evening = rng.random(count) < 0.5
            hours = np.where(evening, rng.normal(21.5, 1.0, count), rng.normal(11.5, 1.5, count))
            hours = np.clip(hours, 8, 23.9)
        else:
            afternoon = rng.random(count) < 0.3
            hours = np.where(afternoon, rng.normal(16, 1.5, count), rng.normal(10.5, 1.5, count))
            hours = np.clip(hours, 7, 20.9)
        local = (hours * HOUR).astype(np.int64)
        return np.sort(epoch(day) + local - self.calendar.utc_offset(day) * HOUR)

    def lifecycle(
        self, rng: np.random.Generator, placed: np.ndarray, lead_days: np.ndarray
    ) -> Schedule:
        """Confirmation, cancellation, shipping and delivery times of a batch of orders."""
        n = len(placed)
        rates = self.config.demand.lifecycle
        confirmed = placed + rng.integers(15 * 60, 3 * HOUR, n)
        cancelled_mask = rng.random(n) < rates.cancellation_rate
        cancelled = np.where(cancelled_mask, placed + rng.integers(30 * 60, 20 * HOUR, n), NONE)
        confirmed = np.where(cancelled_mask & (confirmed >= cancelled), NONE, confirmed)

        # Shipping: the next morning, Sunday excluded; delivery after the lead time.
        offset = self.calendar.utc_offset_hours * HOUR
        placed_local_day = (placed + offset) // DAY
        ship_day = placed_local_day + 1
        ship_day += ((ship_day + 3) % 7 == 6).astype(np.int64)  # epoch day 0 was a Thursday
        shipped = ship_day * DAY + rng.integers(6 * HOUR, 10 * HOUR, n) - offset
        late = rng.random(n) < rates.late_delivery_rate
        delay = lead_days + np.where(late, rng.integers(1, 3, n), 0)
        delivered = (ship_day + delay) * DAY + rng.integers(9 * HOUR, 18 * HOUR, n) - offset
        promised = (ship_day + lead_days) * DAY

        partial = rng.random(n) < rates.partial_delivery_rate
        fraction = np.where(partial, rng.uniform(0.85, 0.99, n), 1.0)
        never_shipped = cancelled_mask
        return Schedule(
            confirmed_at=confirmed,
            shipped_at=np.where(never_shipped, NONE, shipped),
            delivered_at=np.where(never_shipped, NONE, delivered),
            cancelled_at=cancelled,
            promised_on=promised,
            delivered_fraction=fraction,
        )

    def returns(
        self, rng: np.random.Generator, lines: Lines, delivered_at: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Returned lines: (line index, quantity, returned_at, reason index)."""
        line_delivered = delivered_at[lines.order]
        candidates = np.flatnonzero(
            (line_delivered != NONE)
            & (rng.random(len(lines.order)) < self.config.demand.lifecycle.return_rate)
        )
        quantity = np.maximum(1, rng.binomial(lines.quantity[candidates], 0.3))
        returned_at = line_delivered[candidates] + rng.integers(DAY, 10 * DAY, len(candidates))
        reason = rng.choice(len(RETURN_REASONS), size=len(candidates), p=RETURN_REASON_WEIGHTS)
        return candidates, quantity, returned_at, reason


def to_iso(timestamps: np.ndarray) -> list[str | None]:
    """Epoch seconds to timestamptz literals; NONE becomes None (SQL NULL)."""
    text = timestamps.astype("datetime64[s]").astype(str)
    return [None if ts == NONE else f"{t}+00" for ts, t in zip(timestamps, text, strict=True)]


def to_date(timestamps: np.ndarray) -> list[str]:
    return [str(d) for d in timestamps.astype("datetime64[s]").astype("datetime64[D]")]


def cents(values: np.ndarray) -> list[str]:
    return [f"{v // 100}.{v % 100:02d}" for v in values.tolist()]


def days(start: date, end: date) -> list[date]:
    """Every day from start (inclusive) to end (exclusive)."""
    return [start + timedelta(days=i) for i in range((end - start).days)]
