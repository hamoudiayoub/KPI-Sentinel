# ADR-0008 — Transactional outbox to publish platform events

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

When `platform-api` creates an investigation, it must both store it in the database and publish `investigation.requested`. Writing to the database and then to Kafka (dual write) can lose the event, or publish an event for a rolled-back transaction.

## Decision

An `outbox_events` table written in the same transaction as the aggregate; a second Debezium connector reads this table and publishes through the *Outbox Event Router* SMT.

## Alternatives considered

- **Direct publication after commit**: simple, but events can be lost if Kafka is unavailable.
- **Kafka + database transactions (XA)**: complex and poorly supported.
- **Application polling of the outbox table**: works, but adds latency and code; Debezium is already in place.

## Consequences

- No lost or phantom events; at-least-once delivery, hence idempotent consumers.
- Reuses the existing CDC infrastructure.
