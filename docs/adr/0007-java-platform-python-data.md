# ADR-0007 — Java for the platform and the agent, Python for data

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

The platform needs robust, strongly typed services with mature security and messaging support, while the data and statistics ecosystem is Python-first.

## Decision

- **Java 21 + Spring Boot 3**: `platform-api`, `agent-service` (Spring AI), and the `semantic-core` and `events-java` libraries.
- **Python 3.12**: generator, Spark jobs, dbt, Dagster, anomaly detector, evaluation harness and baselines.
- **TypeScript + React**: user interface.

## Alternatives considered

- **All Python** (FastAPI + LangGraph): richer AI ecosystem, but weaker typing and enterprise integration for the platform services.
- **All Java**: possible for detection, but statsmodels and the data ecosystem are in Python.

## Consequences

- Contracts (events, OpenAPI, YAML metrics) are the boundary between languages; they must be validated in CI on both sides.
- Two build toolchains; CI filters them by path.
