# ADR-0004 — Spark Structured Streaming for bronze and silver

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

CDC events must be written to Iceberg and then applied (upsert, delete) to current-state tables, with recovery after failure and no duplicates.

## Decision

PySpark Structured Streaming in 30 s micro-batches: a bronze job (Kafka → `bronze.cdc_events`) and a silver job (incremental read of bronze, one `MERGE INTO` per table inside `foreachBatch`). Checkpoints stored in MinIO.

## Alternatives considered

- **Apache Flink**: true event-at-a-time streaming and advanced state; harder to operate and less necessary with a freshness target of a few minutes. Kept as a possible evolution.
- **Kafka Connect Iceberg Sink**: less code, but less control over the MERGE logic and less learning material.
- **Kafka Streams**: suited to Kafka → Kafka transformations, not to writing into a lakehouse.

## Consequences

- Effectively exactly-once thanks to checkpoints and idempotent Iceberg commits; the LSN-ordered MERGE protects against replays.
- Python on the data side, consistent with dbt, the detector and the evaluation.
