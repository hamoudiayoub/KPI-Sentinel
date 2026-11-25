"""Tests of the history generation, in memory (no database).

The `statistical` tests generate a full 18-month history at reduced scale and check the
properties the detector and the agent rely on.
"""

from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pytest

from sentinel_gen.calendar import load_calendar
from sentinel_gen.demand import NONE, DemandModel, Promotions, epoch
from sentinel_gen.history import (
    generate_history,
    months_before,
    order_status,
    plan_prices,
    plan_promotions,
)
from sentinel_gen.market import market_from_reference
from sentinel_gen.reference import generate_reference_data

SEED = 42


@pytest.fixture(scope="module")
def calendar():
    return load_calendar()


@pytest.fixture(scope="module")
def market(config):
    return market_from_reference(config, generate_reference_data(config, SEED), SEED)


@pytest.fixture(scope="module")
def model(config, calendar, market):
    return DemandModel(config, calendar, market)


def history(config, calendar, market, start, end, scale):
    prices = plan_prices(config, market, start, end, SEED)
    promotions = plan_promotions(config, market, start, end, SEED)
    return list(
        generate_history(config, calendar, market, start, end, SEED, scale, prices, promotions)
    )


def test_months_before_starts_on_the_first_of_the_month():
    assert months_before(date(2026, 11, 1), 18) == date(2025, 5, 1)
    assert months_before(date(2026, 1, 15), 1) == date(2025, 12, 1)


def test_calendar_marks_ramadan_eid_and_holidays(calendar):
    assert calendar.is_ramadan(date(2026, 2, 19))
    assert calendar.is_ramadan(date(2026, 3, 19))
    assert not calendar.is_ramadan(date(2026, 3, 20))
    assert calendar.eid_days[date(2026, 3, 20)] == 1
    assert calendar.days_before_eid(date(2026, 5, 20)) == 7
    assert calendar.is_holiday(date(2026, 7, 30))
    assert calendar.is_holiday(date(2026, 10, 31))
    assert not calendar.is_holiday(date(2025, 10, 31))  # Unity Day starts in 2026
    assert calendar.utc_offset(date(2026, 3, 1)) == 0
    assert calendar.utc_offset(date(2026, 4, 1)) == 1


def test_eid_and_sunday_lower_the_order_rate(model):
    weekday = date(2026, 3, 4)  # Wednesday in Ramadan
    assert model.channel_factors(date(2026, 3, 20)).mean() < 0.4  # first day of Eid al-Fitr
    assert model.channel_factors(date(2026, 4, 5))[0] < model.channel_factors(date(2026, 4, 6))[0]
    assert model.channel_factors(weekday)[2] < model.channel_factors(weekday)[1]  # HoReCa


def test_basket_amounts_are_consistent(model, market):
    rng = np.random.default_rng(1)
    channels = rng.integers(0, 4, 500)
    lines = model.basket(
        rng,
        date(2026, 6, 1),
        channels,
        market.product_price_cents,
        Promotions.none(market.products),
    )
    assert (lines.quantity > 0).all()
    assert (lines.gross_cents == lines.quantity * lines.unit_price_cents).all()
    assert (lines.discount_cents >= 0).all()
    assert (lines.discount_cents <= lines.gross_cents).all()
    keys = lines.order * market.products + lines.product
    assert len(np.unique(keys)) == len(keys)  # one line per product in an order
    for order in np.unique(lines.order)[:50]:
        numbers = lines.line_number[lines.order == order]
        assert list(numbers) == list(range(1, len(numbers) + 1))


def test_promotions_apply_their_discount(model, market):
    rng = np.random.default_rng(2)
    promotions = Promotions.none(market.products)
    promotions.pct[:, :] = 10
    promotions.promotion_id[:, :] = 7
    lines = model.basket(
        rng, date(2026, 6, 1), np.zeros(200, dtype=int), market.product_price_cents, promotions
    )
    small = lines.quantity < 50  # no volume discount
    expected = np.floor(lines.gross_cents[small] * 0.10)
    assert (lines.discount_cents[small] == expected).all()
    assert (lines.promotion_id == 7).all()


def test_lifecycle_is_ordered_in_time(model, market):
    rng = np.random.default_rng(3)
    placed = model.place_times(rng, date(2026, 6, 3), 2000)
    schedule = model.lifecycle(rng, placed, np.full(2000, 2))
    shipped = schedule.shipped_at != NONE
    confirmed = schedule.confirmed_at != NONE
    assert (schedule.confirmed_at[confirmed] > placed[confirmed]).all()
    assert (schedule.shipped_at[shipped] > schedule.confirmed_at[shipped]).all()
    assert (schedule.delivered_at[shipped] > schedule.shipped_at[shipped]).all()
    cancelled = schedule.cancelled_at != NONE
    assert not (cancelled & shipped).any()
    assert 0.01 < cancelled.mean() < 0.06


def test_orders_are_placed_in_business_hours(model):
    rng = np.random.default_rng(4)
    day = date(2026, 6, 3)
    placed = model.place_times(rng, day, 1000)
    local_hours = (placed - epoch(day) + 3600) / 3600  # UTC+1 outside Ramadan
    assert local_hours.min() >= 7
    assert local_hours.max() < 21


def test_status_follows_the_latest_step_before_the_cutoff():
    at = {
        "placed_at": np.array([0, 0, 0, 0]),
        "confirmed_at": np.array([10, 10, 10, NONE]),
        "shipped_at": np.array([20, 20, NONE, NONE]),
        "delivered_at": np.array([30, NONE, NONE, NONE]),
        "cancelled_at": np.array([NONE, NONE, NONE, 5]),
    }
    assert list(order_status(at, cutoff=100)) == ["DELIVERED", "SHIPPED", "CONFIRMED", "CANCELLED"]


def test_the_same_seed_gives_the_same_history(config, calendar, market):
    start, end = date(2026, 1, 1), date(2026, 2, 1)
    first = history(config, calendar, market, start, end, 0.05)
    second = history(config, calendar, market, start, end, 0.05)
    assert [b.orders for b in first] == [b.orders for b in second]
    assert [b.lines for b in first] == [b.lines for b in second]


def test_history_rows_are_valid(config, calendar, market):
    start, end = date(2026, 9, 1), date(2026, 11, 1)
    batches = history(config, calendar, market, start, end, 0.05)
    orders = {o[0]: o for b in batches for o in b.orders}
    for order in orders.values():
        status, placed, _confirmed, shipped, delivered, cancelled = order[5:]
        assert placed < epoch_iso(end)
        if status == "DELIVERED":
            assert delivered is not None and delivered < epoch_iso(end)
        if status == "CANCELLED":
            assert cancelled is not None and shipped is None
    for line in (line for b in batches for line in b.lines):
        assert line[0] in orders
        assert float(line[7]) <= float(line[6])
    for delivery in (d for b in batches for d in b.deliveries):
        order = orders[delivery[0]]
        assert order[7] is not None  # confirmed
        assert (delivery[3] == "FAILED") == (order[5] == "CANCELLED")
    for returned in (r for b in batches for r in b.returns):
        assert orders[returned[0]][5] == "DELIVERED"


def epoch_iso(day):
    return f"{day.isoformat()} 00:00:00+00".replace(" ", "T", 1)


# --- Statistical properties --------------------------------------------------------------


@pytest.fixture(scope="module")
def full_history(config, calendar, market):
    end = config.demand.history.end
    return history(config, calendar, market, months_before(end, 18), end, 0.3)


def daily_totals(batches, category_of_product=None):
    """Daily revenue, or daily units per category, from the generated rows."""
    order_day = {o[0]: o[6][:10] for b in batches for o in b.orders}
    revenue = defaultdict(float)
    units = defaultdict(lambda: defaultdict(int))
    for line in (line for b in batches for line in b.lines):
        day = order_day[line[0]]
        revenue[day] += float(line[6]) - float(line[7])
        if category_of_product is not None:
            units[category_of_product[line[2]]][day] += line[4]
    return revenue, units


@pytest.mark.statistical
def test_daily_revenue_has_a_weekly_pattern(full_history):
    revenue, _ = daily_totals(full_history)
    series = np.array([revenue[d] for d in sorted(revenue)])
    centered = series - series.mean()
    lag7 = np.dot(centered[7:], centered[:-7]) / np.dot(centered, centered)
    assert lag7 > 0.3


@pytest.mark.statistical
def test_ramadan_effect_matches_the_configuration(config, calendar, market, full_history):
    keys = [c.key for c in config.categories]
    category_of_product = {
        int(pid): keys[k]
        for pid, k in zip(market.product_ids, market.product_category, strict=True)
    }
    _, units = daily_totals(full_history, category_of_product)
    start, end = next((s, e) for s, e in calendar.ramadan if s.year == 2026)
    during = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    before = [(start - timedelta(days=i)).isoformat() for i in range(1, 29)]

    def ratio(category):
        return (
            sum(units[category][d] for d in during)
            / len(during)
            / (sum(units[category][d] for d in before) / len(before))
        )

    controls = [k for k in keys if k not in config.demand.ramadan.category_uplift]
    controls = [k for k in controls if k not in config.demand.seasonality]
    control_ratio = np.mean([ratio(k) for k in controls])
    for category, uplift in config.demand.ramadan.category_uplift.items():
        measured = ratio(category) / control_ratio - 1
        assert abs(measured - uplift) <= 0.05, (category, measured, uplift)


@pytest.mark.statistical
def test_volume_at_full_scale_is_in_the_target_range(full_history):
    lines = sum(len(b.lines) for b in full_history)
    assert 1_500_000 <= lines / 0.3 <= 3_000_000
