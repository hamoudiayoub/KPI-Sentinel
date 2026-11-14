# ADR-0009 — In-house semantic layer

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

The agent must reason about metrics defined once, with their allowed dimensions and above all their decomposition tree (revenue = orders × average basket…). It must also compute exact contributions to a deviation.

## Decision

Metrics in YAML validated by JSON Schema; a Java library, `semantic-core`, that compiles them to Trino SQL and implements decomposition (additive, multiplicative with LMDI, mix and rate effects) and contribution analysis by dimension.

## Alternatives considered

- **dbt Semantic Layer / MetricFlow**: a standard, but the full API is tied to dbt Cloud and the decomposition tree is not native.
- **Cube**: very complete, but one more service and no deviation decomposition.
- **Let the LLM write all the SQL**: quick to start, but inconsistent definitions and hallucinated formulas.

## Consequences

- Full control over decomposition, which is at the heart of the product's value.
- More code to maintain and test (property-based tests on decompositions).
