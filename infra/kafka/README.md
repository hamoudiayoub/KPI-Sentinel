# infra/kafka

Topic declarations (`topics.yaml`: partitions, retention, compaction) and partitioning tests of the KRaft cluster.

- `topics.yaml`: application topics, applied idempotently by the `kafka-init` service (`apply_topics.py`, image built from `init/Dockerfile`).
- `tests/`: unit tests of the topic planning, and integration tests of replication and node failures (`make test-integration`).

Design and guarantees: [docs/kafka.md](../../docs/kafka.md).
