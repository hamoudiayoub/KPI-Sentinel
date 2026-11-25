# Demand model

How the generator decides who orders, what, when, and what happens to each order. Parameters live in [`config/atlas.yaml`](config/atlas.yaml) (`channels` and `demand`); the code is in [`src/sentinel_gen/demand.py`](src/sentinel_gen/demand.py), shared by the history backfill and the live stream. Holidays, Ramadan and Eid come from the shared calendar [`semantic/calendar/morocco.yaml`](../../semantic/calendar/morocco.yaml).

## Who orders: daily order rate

Each point of sale *c* of channel *h* places, on day *d*, a Poisson number of orders with mean

```
λ(c, d) = orders_per_day(h) × size(c) × weekday(h, d) × trend(d) × event(h, d) × shock(d) × scale
```

| Factor | Meaning | Value |
|---|---|---|
| `orders_per_day(h)` | Base order frequency of the channel | 0.28 traditional (about every 3.5 days), 0.90 modern trade, 0.35 HoReCa, 0.60 e-commerce |
| `size(c)` | Hidden size of the point of sale, log-normal with mean 1 (σ = 0.5), derived from the seed | — |
| `weekday(h, d)` | Weekly profile per channel; Sunday is very low for B2B channels | e.g. traditional `[1.15, 1.10, 1.05, 1.10, 0.85, 1.05, 0.35]` (Monday first) |
| `trend(d)` | Organic growth | +6 % per year |
| `event(h, d)` | Calendar effect, see below | — |
| `shock(d)` | Market-wide daily shock, gamma with mean 1 (shape 40), shared by all points of sale | coefficient of variation ≈ 16 % |

Combining Poisson counts with a gamma shock and log-normal sizes gives over-dispersed (negative binomial-like) daily volumes, as real order data is.

### Calendar effects

| Day | Effect on the order rate |
|---|---|
| Public holiday | × 0.5 |
| The 7 days before the first day of an Eid | × 1.25 (stocking up) |
| First day of Eid al-Fitr or Eid al-Adha | × 0.25 |
| Following Eid days | × 0.6 |
| Ramadan | × 1.05 traditional, × 1.10 modern trade, × 0.70 HoReCa (cafés closed during the day), × 1.15 e-commerce |

## What is ordered: baskets

An order of channel *h* on day *d* gets, for each category *k*, a Poisson number of lines with mean

```
lines_per_order(h) × weight(k) × season(k, d) × ramadan(k, d)
```

- `weight(k)`: share of the category in the lines (beverages 18 %, dry grocery 18 %, water 14 %, dairy 14 %, personal care 10 %, household 9 %, confectionery 9 %, canned food 8 %).
- `season(k, d) = 1 + A × cos(2π (day_of_year − peak) / 365.25)`: summer peak around 19 July for beverages (A = 0.25) and water (A = 0.30).
- `ramadan(k, d)`: +25 % dairy and +20 % dry grocery during Ramadan.

Because categories are drawn independently, a category effect changes that category's volume without diluting the others; it can be measured by comparing with categories that have no effect (difference in differences, see the tests).

Within a category, products are drawn with a Zipf-like popularity (`1 / rank^0.8`, ranks derived from the seed). A product on promotion has its weight multiplied by 1.6. Quantities are `1 + Poisson(units_per_line(h) − 1)` packs (3 traditional, 20 modern trade, 4 HoReCa, 6 e-commerce). A product drawn twice in an order becomes one line with the summed quantity.

## Prices and discounts

- Every product starts the history at its catalog price, recorded as a first `price_changes` row; each product then gets on average 1.2 increases of 2 to 8 %, half of them in early January. `products.list_price` ends at the latest price.
- About 6 promotions a month on popular products, 7 to 21 days long, 5 to 20 % off, 30 % of them limited to one channel.
- Line amounts are exact, in cents: `gross = quantity × unit_price`; `discount = floor(gross × (promotion % + volume %))`, with a volume discount of 3 % from 50 packs and 5 % from 100 packs, never above the gross amount.

## When: order time and lifecycle

Orders arrive in two waves, around 10:30 and 16:00 local time. During Ramadan the second wave moves to the evening (around 21:30), after the fast is broken. Moroccan clocks are UTC+1, and UTC+0 during Ramadan; timestamps are stored in UTC.

| Step | Rule |
|---|---|
| Confirmation | 15 minutes to 3 hours after the order |
| Cancellation | 3 % of orders, 30 minutes to 20 hours after the order (before or after confirmation) |
| Shipping | The next morning (06:00 to 10:00), Sunday excluded |
| Promised date | Shipping day + lead time of the warehouse (1 day Casablanca, 2 days elsewhere) + extra days for remote regions |
| Delivery | On the promised date, 09:00 to 18:00; 8 % of deliveries are 1 or 2 days late |
| Partial delivery | 3 % of orders receive 85 to 99 % of the ordered units |
| Returns | 1.5 % of delivered lines, 1 to 10 days after delivery, about 30 % of the line's units, with a reason |

The backfill stops at its end date: orders keep the status reached by then (`PLACED`, `CONFIRMED`, `SHIPPED`, `DELIVERED` or `CANCELLED`), and later steps are not written. A delivery row exists once an order is confirmed; its status follows the order (`SCHEDULED`, `IN_TRANSIT`, `DELIVERED`), and it becomes `FAILED` when a confirmed order is cancelled.

## Determinism

Each day draws from its own generator, seeded by `(seed, day)`; prices, promotions, sizes and popularity have their own streams. The same seed, scale and end date always produce the same history, whatever the batching.

## Measured properties (seed 42, 18 months to 2026-11-01, scale 1.0)

| Property | Value |
|---|---|
| Orders / order lines | about 403,000 / 2,556,000 |
| Lag-7 autocorrelation of daily revenue | 0.53 (weekly pattern) |
| Ramadan 2026 effect on dairy / dry grocery, measured against unaffected categories | +23.8 % / +20.1 % (configured +25 % / +20 %) |

The tests in `tests/test_history.py` (marker `statistical`) recompute these properties at 30 % scale.
