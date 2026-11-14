# ADR-0010 — Guided-loop agent, implemented with Spring AI

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

The agent must be reliable, measurable, cheap and safe. A fully free-form agent explores poorly, costs a lot and is hard to test.

## Decision

- A three-phase loop: deterministic pre-analysis (decomposition, contributions, quality, calendar), LLM reasoning with typed tools (hypotheses, checks), and a conclusion through a `submit_report` tool with a strict schema.
- Explicit budgets (tool calls, tokens, duration).
- Spring AI for provider abstraction (Anthropic by default, Ollama locally) and tool calling.
- CI tests on replayed transcripts, never on a real LLM.

## Alternatives considered

- **Single prompt with pre-aggregated data**: kept as a baseline in the benchmark.
- **LangGraph in Python**: rich ecosystem, but one more Python service next to a Java platform.
- **Fine-tuning**: expensive, and of little use until the benchmark identifies a specific weakness.

## Consequences

- Predictable behavior, comparable across models.
- The benchmark can measure the contribution of each phase (ablations).
