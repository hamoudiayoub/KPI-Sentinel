# Engineering standards

These rules apply to every change in the repository.

## 1. Definition of Done

- [ ] The change does what it claims, with evidence in the pull request.
- [ ] Tests added: unit tests for logic, integration tests for every I/O (Testcontainers or the compose stack).
- [ ] Line coverage ≥ 80 % on new domain code (JaCoCo, pytest-cov).
- [ ] `make lint` and `make test` pass locally; CI green.
- [ ] No secrets, generated data or build output committed.
- [ ] Documentation up to date: component README, architecture if a component or contract changes, runbook if it is operational, ADR if a structural decision was made.
- [ ] Contracts (OpenAPI, event schemas, dbt contracts) up to date and backward compatible.
- [ ] Observability: structured logs, metrics and traces for every new service or flow.

## 2. Git

- **Trunk-based**: `main` is always deployable; short-lived branches (under 3 days).
- Naming: `<type>/<short-description>`, with `type` ∈ `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.
- **Conventional Commits**: `<type>(<scope>): <description>`. Scopes: `repo`, `infra`, `generator`, `ingestion`, `streaming`, `dbt`, `semantic`, `platform`, `detector`, `agent`, `eval`, `web`, `obs`, `security`.
- **Squash** merge only; the PR title becomes the commit message.
- `main` protection: PR required, `ci-ok` check required, linear history, no force push.

### Protecting `main`

Configured once by a repository administrator, after the CI workflow has run at least once (GitHub only offers a status check it has already seen):

1. **Settings → Rules → Rulesets → New ruleset → New branch ruleset**, name `main`, enforcement **Active**.
2. **Target branches**: add **Include default branch**.
3. Enable these rules:
   - **Restrict deletions**.
   - **Require linear history**.
   - **Require a pull request before merging**, with **Allowed merge methods** set to **Squash** only.
   - **Require status checks to pass**, with **Require branches to be up to date before merging**, and add the check **`ci-ok`** only. The other jobs run only when their files change, so requiring them would block pull requests that skip them.
   - **Block force pushes**.
4. **Settings → General → Pull Requests**: allow squash merging only, and enable **Automatically delete head branches**.

### Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on every push to `main`. A first job detects which parts of the repository changed; the `java`, `python` and `dbt` jobs run only when their files changed, and call the same `make` targets as a workstation. The `ci-ok` job aggregates the results: it fails if any job failed or was cancelled, and passes if every job succeeded or was skipped. A new push to a pull request cancels its previous run. Third-party actions are pinned by commit SHA, with the release tag in a comment.

## 3. Pull requests

- One coherent change per PR. Ideal diff < 600 lines excluding generated files; above that, split.
- `.github/pull_request_template.md` filled in completely.
- Review checklist:
  - Does the code do what the PR says, and only that?
  - Are names and structure understandable without an oral explanation?
  - Are error cases handled (timeouts, duplicates, missing data)?
  - Would the tests fail if the behavior regressed?
  - Is the change observable in production (logs, metrics)?
  - Is there a security risk (injection, secret, overly broad permission)?

## 4. Testing strategy

| Level | Java | Python | SQL / dbt |
|---|---|---|---|
| Unit | JUnit 5, AssertJ, jqwik (properties) | pytest, hypothesis | — |
| Integration | Testcontainers (Postgres, Kafka, Trino), Spring Boot Test | pytest + Testcontainers or the compose stack | `dbt build` on test data |
| Contract | JSON Schema validation of events, OpenAPI diff | JSON Schema validation | dbt contracts (`contract.enforced`) |
| Architecture | ArchUnit (hexagonal layers) | — | — |
| End to end | `make demo` scenario | Evaluation harness | Source ↔ gold reconciliation |
| Agent | Replayed LLM transcripts, never a network call in CI | same | — |

Rules: at least one test per behavior; no database mocks; test data built with builders or named fixtures; deterministic tests (fixed seeds, injected clock).

## 5. Code conventions

### Language

- Everything is written in English: code, identifiers, comments, documentation, commit messages and PRs.

### Java

- Java 21, Spring Boot 3, root package `io.kpisentinel.<service>`.
- Hexagonal architecture: `domain` (no Spring dependency), `application` (use cases, ports), `adapters.in.web`, `adapters.in.kafka`, `adapters.out.persistence`, `adapters.out.trino`, `adapters.out.kafka`. Rules enforced by ArchUnit.
- `record` for value objects and DTOs; constructor injection; no `@Autowired` on fields.
- google-java-format formatting through Spotless.
- Virtual threads enabled; no `synchronized` around blocking calls (pinning).

### Python

- Python 3.12, uv, ruff (lint + format), type annotations everywhere, `pydantic` / `pydantic-settings` for models and configuration.
- Packages under `src/<package_name>/`, CLI with Typer, structured JSON logs.

### SQL and dbt

- sqlfluff, trino dialect; lowercase keywords, named CTEs, a `final` CTE at the end of each model.
- Prefixes: `stg_<source>__<table>`, `int_`, `fct_`, `dim_`, `agg_`; snake_case columns; amounts suffixed with their unit when ambiguous.
- Every model has a description and tests on its key.

### TypeScript

- React, Vite, strict TypeScript, ESLint, Prettier; data fetching with TanStack Query; function components.

## 6. API

- REST, plural resources, versioned with a `/api/v1` prefix.
- Errors as `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, `traceId`.
- Cursor pagination (`?cursor=…&limit=…`, response with `nextCursor`).
- `Idempotency-Key` on creation `POST`s: same key and same body → same response.
- Dates in ISO 8601 UTC; amounts as decimal strings or numbers with an explicit unit.
- OpenAPI specification exported and versioned; a breaking change requires a new version.

## 7. Events

- CloudEvents 1.0, type `sentinel.<domain>.<event>.v<N>`, schema in `contracts/events/`.
- Producers: `acks=all`, idempotence enabled, explicit partition key.
- Consumers: idempotent (`processed_events` table or business uniqueness constraint), offset committed after the side effect, retry with exponential backoff, then dead letter.
- `traceparent` and `tenantid` propagated in headers.

## 8. Configuration, secrets, logs

- Configuration through environment variables, documented in `infra/compose/.env.example` with dummy values.
- No secrets in code, tests, logs or error messages.
- JSON logs with `timestamp`, `level`, `service`, `traceId`, `spanId`, `tenantId`, `message`; no personal data.
- Prometheus metrics named `<service>_<object>_<unit>` (e.g. `agent_investigation_duration_seconds`).

## 9. Documentation

- **ADR** (`docs/adr/`) for any decision that is hard to reverse: choice of a technology, a format, a protocol. Template: `docs/templates/adr.md`.
- **Design doc** (`docs/design/`) before a complex feature (the agent in particular). Template: `docs/templates/design-doc.md`.
- **Runbook** (`docs/runbooks/`) for every alert and every manual operation. Template: `docs/templates/runbook.md`.
- Diagrams in Mermaid, versioned with the code.

## 10. Quality tooling

- Pre-commit hooks: formatting, secret scanning (gitleaks), Conventional Commits check.
- CI: path-filtered jobs and a single `ci-ok` aggregator job (see §2, Continuous integration).
- Supply chain: Dependabot, gitleaks, Trivy, CodeQL.

## 11. Versioning and releases

- SemVer per component, driven by Conventional Commits (release-please).
- Docker images tagged with the version and the SHA; never `latest` in the compose file.
