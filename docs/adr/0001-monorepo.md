# ADR-0001 — Single monorepo

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

The project has about ten components (Java and Python services, pipelines, dbt, infrastructure, docs) built by a single person. Contracts (events, OpenAPI, metrics) are shared between components.

## Decision

A single Git repository, organized by nature (`services/`, `libs/`, `pipelines/`, `infra/`, `contracts/`, `semantic/`). Java built as a Maven multi-module project, Python as a uv workspace, CI with path filters.

## Alternatives considered

- **One repository per service**: strong isolation, but high coordination cost, duplicated contracts and a fragmented overall view.

## Consequences

- A contract and its producers and consumers change atomically in a single PR.
- A single code review covers a change end to end.
- CI must stay fast thanks to path filters; to be monitored.
