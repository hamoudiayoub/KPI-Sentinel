# Product vision — KPI Sentinel

## Problem

At a consumer goods distributor, when weekly revenue drops by 8 %, the sales leadership asks "why?". An analyst then spends between half a day and two days slicing the data by region, channel, category and sales rep, checking that the data is not wrong, and writing a summary. Meanwhile the cause (stock-out, a sales rep leaving, a price increase…) keeps costing money.

## Value proposition

KPI Sentinel continuously monitors sales indicators, detects abnormal deviations and launches an AI agent that runs the investigation like an analyst would: it decomposes the metric, tests hypotheses with queries, rules out false leads (seasonality, data incident) and delivers, in under two minutes, a quantified, sourced explanation with a confidence level.

## Demo context

**Atlas Distribution** (fictional company): an FMCG distributor in Morocco with 5 warehouses, about 2,000 points of sale (convenience stores, modern retail, HoReCa, e-commerce), about 300 SKUs and 40 sales reps. The data is entirely simulated, with injected scenarios whose cause is known: this is what makes it possible to measure the agent's quality objectively.

## Users

| Persona | Need | What Sentinel gives them |
|---|---|---|
| Sales director | Quickly know why a KPI moves and what to do | Alert and summary in French, with recommended actions |
| BI analyst | Save time on diagnosis without losing control | Traceable investigation, queries and evidence available for review |
| Data engineer | Tell a real business problem from a data incident | The agent checks freshness, dbt tests and CDC lag before concluding |

## Job stories

- When a region's weekly revenue drops, I want to know the three most likely causes and their weight, so that I can decide on an action the same day.
- When an alert fires during Ramadan, I want to know whether the deviation exceeds the expected seasonal effect, so that I do not react to noise.
- When a number looks wrong, I want to know whether the data is reliable before alerting management.

## Goals and success metrics (v1.0)

| Goal | Measure | Target |
|---|---|---|
| Correct diagnosis | Root cause in the top 3, 50-scenario benchmark | ≥ 75 % |
| Better than simple approaches | Top-3 gap against the Adtributor baseline | ≥ +20 points |
| Fast | p95 duration of an investigation | ≤ 120 s |
| Grounded in data | Findings backed by verified evidence | ≥ 95 % |
| Cost-effective | Average LLM cost per investigation | Measured and published, target ≤ 0.15 USD |
| Reliable | Freshness of gold tables | ≤ 60 min, 99 % of the time |
| Low noise | False positives on negative controls (Ramadan, public holidays) | ≤ 1 per metric per month |

## Scope v1.0

**Included**: real-time CDC ingestion, lakehouse, tested dbt models, semantic layer with a metric tree, statistical detection, investigation agent, structured report, web interface, observability, benchmark.

**Excluded**: sales forecasting, causal inference in the strict statistical sense (we talk about probable causes and attribution), automatic actions on source systems, connectors to real ERPs, mobile app.

## Hypotheses to validate

1. A guided loop (deterministic pre-analysis, then LLM reasoning with tools) beats both a single prompt and a statistical algorithm alone.
2. Checking data quality before concluding sharply reduces false explanations.
3. An explicit semantic layer (metric tree) matters more for agent reliability than the choice of model.

The benchmark is designed to confirm or refute each of these hypotheses.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Stack too heavy for a laptop | Blocks development | Docker Compose profiles, adjustable data scale, `docs/04-prerequisites.md` |
| Scope creep | Project never finished | Demonstrable milestones, MoSCoW priorities |
| LLM cost | Budget | Spending cap, replayed tests in CI, small models during development |
| Agent hallucinations | Credibility | Groundedness validation, mandatory evidence, benchmark |
| Incompatible versions (Spark, Iceberg, Nessie, Trino) | Lost time | Version matrix verified and documented in the architecture |

## Glossary

- **CDC** (Change Data Capture): capturing a database's changes from its transaction log.
- **Lakehouse**: object storage plus a transactional table format (Iceberg), queryable in SQL.
- **Medallion**: organizing data in bronze (raw), silver (cleaned) and gold (analysis-ready) layers.
- **Semantic layer**: a single, versioned definition of metrics and dimensions.
- **Metric tree**: decomposition of a KPI into factors (revenue = orders × average basket…).
- **RCA** (root cause analysis): finding the underlying causes of a deviation.
- **Groundedness**: every statement in the report is linked to evidence produced by a tool.
- **MAD**: Moroccan dirham, the currency of all amounts.
