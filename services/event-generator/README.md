# services/event-generator

Python: generates reference data, 18 months of history, the real-time order stream and anomaly scenarios with ground truth in the simulated ERP.

The market is described in [`config/atlas.yaml`](config/atlas.yaml): the 12 regions of Morocco and their main cities, 5 warehouses, 40 sales reps, 2,000 points of sale split by channel, 8 categories, 15 fictional brands and 300 SKUs. Geography is real; every company, person and brand name is fictional.

## Commands

Inside the local stack (the database password comes from `infra/compose/.env`):

```bash
make up PROFILE=core
make seed                       # reference data, seed 42
make seed SEED=7 FORCE=1        # replace everything with another seed
make gen ARGS="backfill"        # 18 months of order history (about 2.5 million order lines)
make gen ARGS="fingerprint"     # SHA-256 of each table's content
```

From the host, with the `SENTINEL_GEN_DB_*` variables set (`HOST`, `PORT`, `NAME`, `USER`, `PASSWORD`):

```bash
uv run --package event-generator sentinel-gen seed --seed 42 [--force]
```

| Command | What it does |
|---|---|
| `seed` | Loads geography, warehouses, sales reps, customers, brands, categories, products and opening stock, in one transaction. Refuses to touch a non-empty ERP unless `--force`, which empties every ERP table first. |
| `backfill` | Generates the order history before `--end` (default 2026-11-01): price changes, promotions, orders, lines, deliveries and returns, one transaction per month. `--months 18`, `--scale 1.0` (order volume), `--seed 42`. Refuses to touch existing transactions unless `--force`. The model is described in [MODEL.md](MODEL.md). |
| `fingerprint` | Prints a SHA-256 per table, computed on the business content (audit timestamps and database-assigned keys excluded), to compare two runs. |

## Determinism

One seeded random generator is consumed in a fixed order, and every row carries an explicit id, so the same seed always gives the same data, down to the fingerprint. Rows are loaded with `COPY` through a temporary table, then inserted with `OVERRIDING SYSTEM VALUE` to keep the generated ids; identity sequences are moved past them.

## Tests

```bash
uv run pytest services/event-generator -m "not integration"   # pure, no network or Docker
uv run pytest services/event-generator -m integration         # Testcontainers Postgres + ERP migrations
```
