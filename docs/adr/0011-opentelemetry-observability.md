# ADR-0011 — Observability with OpenTelemetry, optional Langfuse

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

We need to follow a flow that crosses HTTP, Kafka, Trino and LLM calls, and to measure the agent's cost and latency.

## Decision

- OpenTelemetry instrumentation everywhere (Java agent, Python SDK), with `traceparent` propagated in Kafka headers.
- OTel Collector → Prometheus (metrics), Tempo (traces), Loki (logs); Grafana for visualization and alerting.
- LLM spans following the OpenTelemetry GenAI semantic conventions; optional Langfuse export behind a flag.

## Alternatives considered

- **Self-hosted Langfuse as the main source**: its recent versions require several extra services (analytical database, cache), too heavy locally.
- **ELK stack**: heavier, less focused on traces.

## Consequences

- A single trace from the detector to the agent's report.
- Agent steps are also persisted in the database (`investigation_steps`) for the interface, independently of observability.
