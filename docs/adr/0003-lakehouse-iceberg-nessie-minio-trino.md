# ADR-0003 — Iceberg lakehouse on MinIO, Nessie catalog, Trino queries

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

We need open, transactional analytical storage that accepts streaming writes (Spark) and batch transformations (dbt), can be queried in SQL by several engines, and keeps version history.

## Decision

- **Apache Iceberg** as the table format.
- **MinIO** as S3-compatible object storage.
- **Project Nessie** as the catalog (JDBC persistence in `postgres-platform`).
- **Trino** as the SQL engine for dbt, the semantic layer and the agent.

## Alternatives considered

- **Delta Lake**: excellent with Spark and decent Trino integration, but Iceberg is more engine-neutral.
- **Iceberg REST catalog**: simpler; Nessie adds data branches, useful for testing transformations without touching production.
- **DuckDB alone**: very light, but does not demonstrate a distributed engine; still usable for local tests.
- **Cloud warehouse** (BigQuery, Snowflake): cost and cloud dependency, contrary to the "everything local" goal.

## Consequences

- The Spark ↔ Iceberg ↔ Nessie ↔ Trino compatibility matrix must be checked and documented.
- Table maintenance is required (small files, snapshots), as a scheduled job.
- Time travel makes it possible to replay an investigation on a past state of the data.
