# ADR-0002 — CDC with Debezium to Kafka in KRaft mode

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

Analytics must reflect the ERP in near real time without loading the production database, and keep the full history of changes (status transitions, stock movements).

## Decision

- Debezium (PostgreSQL connector, `pgoutput` plugin) on Kafka Connect.
- Kafka in KRaft mode (no ZooKeeper), three combined broker + controller nodes, `replication.factor=3`, `min.insync.replicas=2`.
- JSON without an embedded schema at first; moving to Avro and a schema registry will be evaluated later.

## Alternatives considered

- **Batch extraction by query** (`updated_at > last run`): simple, but misses deletes and intermediate states, and loads the source.
- **Application triggers**: tight coupling with the ERP.
- **Redpanda**: lighter and Kafka API compatible, but Kafka remains the industry reference.
- **A single broker**: lighter, but demonstrates neither replication nor fault tolerance.

## Consequences

- At-least-once delivery: consumers must be idempotent.
- The replication slot must be monitored (WAL growth if the connector stops).
- About 1.5 GB of RAM for three brokers locally.
