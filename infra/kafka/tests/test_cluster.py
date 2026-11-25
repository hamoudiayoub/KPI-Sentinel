"""Checks the replication guarantees of the three-node Kafka cluster.

The failure tests stop brokers and always restart them; together they take about two minutes.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration

KAFKA_BIN = "/opt/kafka/bin"
BOOTSTRAP = "kafka-1:29092"
APPLICATION_TOPICS = [
    "sentinel.anomaly.detected.v1",
    "sentinel.investigation.requested.v1",
    "sentinel.investigation.step.v1",
    "sentinel.investigation.completed.v1",
]


@pytest.fixture(scope="module")
def kafka(compose):
    """Runs a Kafka CLI tool inside kafka-1 and returns the completed process."""

    def run(tool, *args, stdin=None, timeout_s=120):
        return compose(
            "exec", "-T", "kafka-1", f"{KAFKA_BIN}/{tool}", "--bootstrap-server", BOOTSTRAP,
            *args, stdin=stdin, timeout_s=timeout_s,
        )  # fmt: skip

    return run


def ok(result):
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture
def probe_topic(kafka):
    """A replicated topic created for one test and deleted afterwards."""
    name = f"probe-{uuid.uuid4().hex[:8]}"
    ok(
        kafka(
            "kafka-topics.sh",
            "--create",
            "--topic",
            name,
            "--partitions",
            "3",
            "--replication-factor",
            "3",
            "--config",
            "min.insync.replicas=2",
        )
    )
    yield name
    kafka("kafka-topics.sh", "--delete", "--topic", name)


def produce(kafka, topic, count, *extra, timeout_s=120):
    lines = "".join(f"message-{i}\n" for i in range(count))
    return kafka(
        "kafka-console-producer.sh", "--topic", topic,
        "--command-property", "acks=all", *extra, stdin=lines, timeout_s=timeout_s,
    )  # fmt: skip


def consume_all(kafka, topic):
    output = ok(
        kafka(
            "kafka-console-consumer.sh",
            "--topic",
            topic,
            "--from-beginning",
            "--timeout-ms",
            "15000",
        )
    )
    return [line for line in output.splitlines() if line.startswith("message-")]


def test_quorum_has_three_voters(kafka):
    status = ok(kafka("kafka-metadata-quorum.sh", "describe", "--status"))
    for node in (1, 2, 3):
        assert f'"id": {node},' in status


@pytest.mark.parametrize("topic", APPLICATION_TOPICS)
def test_application_topics_are_fully_replicated(kafka, topic):
    description = ok(kafka("kafka-topics.sh", "--describe", "--topic", topic))
    header, *partitions = description.strip().splitlines()
    assert "ReplicationFactor: 3" in header
    assert "min.insync.replicas=2" in header
    assert partitions
    for partition in partitions:
        isr = partition.split("Isr:")[1].split()[0]
        assert sorted(isr.split(",")) == ["1", "2", "3"]


@pytest.mark.parametrize(
    "setting",
    [
        "auto.create.topics.enable=false",
        "unclean.leader.election.enable=false",
        "min.insync.replicas=2",
        "default.replication.factor=3",
    ],
)
def test_brokers_refuse_unsafe_defaults(kafka, setting):
    configs = ok(
        kafka(
            "kafka-configs.sh",
            "--describe",
            "--entity-type",
            "brokers",
            "--entity-name",
            "1",
            "--all",
        )
    )
    assert setting in configs


def test_kafka_init_is_idempotent(compose):
    for _ in range(2):
        result = compose("run", "--rm", "kafka-init", timeout_s=180)
        assert result.returncode == 0, result.stderr
        assert "4 topics declared" in result.stdout


def test_one_node_down_loses_nothing(compose, kafka, probe_topic, wait_ready):
    compose("stop", "kafka-2")
    try:
        result = produce(kafka, probe_topic, 100)
        assert result.returncode == 0, result.stderr
        assert len(consume_all(kafka, probe_topic)) == 100
    finally:
        compose("start", "kafka-2")
        wait_ready()


def test_two_nodes_down_refuses_writes(compose, kafka, probe_topic, wait_ready):
    # Two of three nodes down also loses the controller quorum: the in-sync replica set
    # can no longer shrink, so the leader waits for replicas that never answer and the
    # write expires instead of being acknowledged. No write is ever confirmed.
    compose("stop", "kafka-2", "kafka-3")
    try:
        result = produce(
            kafka, probe_topic, 1,
            "--command-property", "request.timeout.ms=10000",
            "--command-property", "delivery.timeout.ms=20000",
            timeout_s=90,
        )  # fmt: skip
        errors = result.stdout + result.stderr
        assert any(
            marker in errors for marker in ("NOT_ENOUGH_REPLICAS", "NotEnoughReplicas", "Expiring")
        ), errors
    finally:
        compose("start", "kafka-2", "kafka-3")
        wait_ready()
    assert consume_all(kafka, probe_topic) == []
