# Architecture Decision Records

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-monorepo.md) | Single monorepo | Accepted |
| [0002](0002-cdc-debezium-kafka-kraft.md) | Debezium CDC to Kafka KRaft | Accepted |
| [0003](0003-lakehouse-iceberg-nessie-minio-trino.md) | Iceberg lakehouse, MinIO, Nessie, Trino | Accepted |
| [0004](0004-spark-structured-streaming.md) | Spark Structured Streaming | Accepted |
| [0005](0005-dbt-trino-medallion.md) | dbt on Trino, medallion | Accepted |
| [0006](0006-dagster-orchestration.md) | Dagster orchestration | Accepted |
| [0007](0007-java-platform-python-data.md) | Java for the platform, Python for data | Accepted |
| [0008](0008-transactional-outbox.md) | Transactional outbox | Accepted |
| [0009](0009-in-house-semantic-layer.md) | In-house semantic layer | Accepted |
| [0010](0010-guided-agent-loop-spring-ai.md) | Guided-loop agent, Spring AI | Accepted |
| [0011](0011-opentelemetry-observability.md) | OpenTelemetry observability | Accepted |
| [0012](0012-keycloak-oidc.md) | OIDC with Keycloak | Accepted |

New ADR: copy `docs/templates/adr.md`, take the next number, add a row here. An accepted ADR is never edited; it is replaced by a new ADR that marks it "Superseded by ADR-XXXX".
