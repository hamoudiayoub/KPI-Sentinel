# Kafka cluster

Three Kafka nodes (`kafka-1`, `kafka-2`, `kafka-3`, image `apache/kafka:4.4.0`) run in KRaft mode in the `core` profile. They carry the change data capture of the ERP and the platform's domain events (ADR-0002).

## KRaft and Raft

Kafka no longer needs ZooKeeper: cluster metadata (topics, partitions, leaders, in-sync replicas) is itself stored in an internal log, `__cluster_metadata`, replicated with the Raft consensus protocol among the **controllers**.

Here each node is both broker and controller (`process.roles=broker,controller`), and the three controllers form the voter set `1@kafka-1:9093, 2@kafka-2:9093, 3@kafka-3:9093`. One controller is the active leader; a metadata change is committed once a **majority** of voters (2 of 3) has written it. Hence:

- one controller down: the remaining two still form a majority, metadata keeps changing (leader elections, in-sync replica updates);
- two controllers down: no majority, the metadata is frozen until a second node returns.

Combined mode keeps the local stack small. In production, controllers usually run on dedicated nodes so that losing brokers never costs the quorum.

```bash
docker compose -f infra/compose/docker-compose.yml exec kafka-1 \
  /opt/kafka/bin/kafka-metadata-quorum.sh --bootstrap-server kafka-1:29092 describe --status
```

## Replication, ISR and acks

Every partition has three replicas (`default.replication.factor=3`): one **leader**, which serves reads and writes, and two **followers**, which copy it. The **in-sync replica set (ISR)** lists the replicas that are caught up; a follower that has not fetched for `replica.lag.time.max.ms` (30 s by default) is removed from it.

A producer chooses how many acknowledgements it waits for:

| `acks` | The write is acknowledged when… | Risk |
|---|---|---|
| `0` | it is sent | Lost on any failure |
| `1` | the leader has written it | Lost if the leader dies before a follower copied it |
| `all` | every replica of the ISR has written it | None, as long as the ISR is large enough |

With `acks=all`, `min.insync.replicas=2` sets "large enough": if the ISR shrinks below two replicas, the leader refuses the write with `NotEnoughReplicas` instead of accepting a write held by a single copy. The platform's producers use `acks=all` with idempotence enabled.

Two more settings protect the data:

- `unclean.leader.election.enable=false`: a replica that is out of the ISR never becomes leader, so no acknowledged write is silently dropped.
- `auto.create.topics.enable=false`: a typo in a topic name fails instead of creating a new, unreplicated topic.

## What happens when nodes go down

Measured on the local stack (`infra/kafka/tests/test_cluster.py`):

| Nodes down | Controllers | Writes with `acks=all` | Reads |
|---|---|---|---|
| 0 | Quorum (3/3) | Accepted | Served |
| 1 | Quorum (2/3) | Accepted. Partitions led by the lost node elect a new leader; their ISR shrinks to two replicas after up to 30 s, during which writes wait | Served; every acknowledged message is read back |
| 2 | No quorum (1/3) | Refused: the producer gets no acknowledgement and the write expires (`REQUEST_TIMED_OUT`, then `Expiring … record(s)`) | Only partitions led by the surviving node |
| 3 | — | Refused | None |

With two nodes down, the failure is a timeout rather than `NotEnoughReplicas`: the leader would have to shrink the ISR to reject the write, but shrinking the ISR is a metadata change, and without a controller quorum no metadata change can commit. Either way, **no write is acknowledged, so no acknowledged data is lost**. When the nodes return, the followers catch up from the leader and rejoin the ISR.

## Topics as code

Application topics are declared in [`infra/kafka/topics.yaml`](../infra/kafka/topics.yaml) and applied by the one-shot `kafka-init` service on every `make up`. Applying is idempotent: missing topics are created, partitions can grow but never shrink, and the declared configs are set on every run. CDC topics (`atlas.erp.*`) are created by Kafka Connect.

| Topic | Partitions | Retention |
|---|---|---|
| `sentinel.anomaly.detected.v1` | 6 | 14 days |
| `sentinel.investigation.requested.v1` | 6 | 14 days |
| `sentinel.investigation.step.v1` | 6 | 7 days |
| `sentinel.investigation.completed.v1` | 6 | 30 days |

## Access

| From | Bootstrap servers |
|---|---|
| Containers on the `sentinel` network | `kafka-1:29092,kafka-2:29092,kafka-3:29092` |
| The host | `localhost:9092,localhost:9094,localhost:9096` (ports from `infra/compose/.env`) |
| Kafka UI | http://localhost:8080 |
