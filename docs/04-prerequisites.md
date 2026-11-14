# Prerequisites

## Machine

| Resource | Minimum | Recommended | Note |
|---|---|---|---|
| RAM | 16 GB | 32 GB | With 16 GB, run profiles two at a time (`core` + `lake`, then `core` + `platform`) |
| CPU | 4 cores | 8 cores | Spark and Trino benefit from more cores |
| Free disk | 40 GB | 80 GB, SSD | Docker images, volumes, simulated data |
| OS | Linux, macOS, or Windows with WSL2 | Linux or macOS | On Windows, keep the repository in the WSL file system |

Docker Desktop: allocate at least 10 GB of RAM (12 GB recommended) in the resource settings.

## Software

| Tool | Purpose | Check |
|---|---|---|
| Git | Version control | `git --version` |
| GitHub CLI (`gh`) | Pull requests, CI runs | `gh --version` |
| Docker Engine or Desktop, Compose v2 | The whole local stack | `docker compose version` |
| GNU make ≥ 4.3 | Project commands | `make --version` |
| JDK 21 (Temurin recommended) | Java services | `java -version` |
| Maven | Provided by the `./mvnw` wrapper | — |
| Python 3.12 and uv | Generator, Spark, dbt, detector, evaluation | `uv --version` |
| Node.js LTS and pnpm | Web interface | `node -v`, `pnpm -v` |
| pre-commit | Quality hooks | `pre-commit --version` |

Useful: IntelliJ IDEA or VS Code, DBeaver (SQL on Postgres and Trino), `kcat` (Kafka inspection), Bruno or HTTPie (API testing).

## Accounts and keys

| Account | What for | Note |
|---|---|---|
| LLM API key (Anthropic) | Running the agent in `agent-service` | Set a monthly spending limit in the provider console |
| Langfuse Cloud (optional) | Viewing LLM traces | Otherwise everything goes through OpenTelemetry and Grafana |
| Slack webhook (optional) | Notifications | Mailpit is enough locally |

The API key only goes in `infra/compose/.env` (never committed); it never appears in code, logs or tests. CI tests replay recorded LLM transcripts and need no key.
