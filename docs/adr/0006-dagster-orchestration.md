# ADR-0006 — Orchestration with Dagster

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

We need to schedule `dbt build`, Iceberg maintenance and detection, with visibility on lineage and freshness.

## Decision

Dagster (webserver + daemon), asset-oriented, with the `dagster-dbt` integration. Silver tables are declared as external assets with a freshness policy. Run storage in `postgres-platform`.

## Alternatives considered

- **Apache Airflow**: the market standard, but task-oriented rather than asset-oriented, and heavier locally. The concepts remain transferable.
- **Scheduler inside platform-api**: simple, but mixes application and data responsibilities.
- **Cron**: no lineage, no retries, no history.

## Consequences

- dbt lineage and freshness are visible in a single interface.
- One more service to operate (~1 GB of RAM).
