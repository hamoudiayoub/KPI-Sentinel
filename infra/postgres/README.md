# infra/postgres

Initialization of both Postgres instances: script that creates the platform databases (`platform`, `keycloak`, `nessie`, `dagster`) and Flyway migrations of the simulated ERP (`source/migrations/`).

- `platform/init/`: runs once, when the platform data volume is created.
- `source/migrations/`: versioned Flyway migrations (`V<n>__<description>.sql`), applied by the `flyway-source` service on every `make up`. An applied migration is never edited: add a new version instead.
- `source/tests/`: integration tests of the schema (`make test-integration`).

Schema documentation: [docs/data-model/erp.md](../../docs/data-model/erp.md).
