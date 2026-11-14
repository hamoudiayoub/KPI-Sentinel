# ADR-0005 — dbt on Trino, medallion architecture

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

Business transformations (cleaning, enrichment, facts, dimensions, aggregates) must be versioned, tested, documented and easy to review.

## Decision

dbt with the `dbt-trino` adapter, Iceberg tables. Layers: `staging` → `intermediate` → `gold`. Generic tests and `dbt_expectations`, contracts enforced on gold models, snapshots for dimensions with history (SCD2). Test results loaded into `quality.dq_results`.

## Alternatives considered

- **Transformations in Spark only**: a single engine, but business logic that is harder to read and test.
- **SQLMesh**: interesting (plans, virtual environments), less widespread in industry.

## Consequences

- Business logic in SQL, easy to review.
- dbt tests become a source for the agent (quality check before concluding).
