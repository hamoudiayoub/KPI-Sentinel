"""Unit tests of the topic planning logic (no Kafka needed)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "apply_topics.py"
TOPICS_FILE = Path(__file__).resolve().parents[1] / "topics.yaml"

# The script runs standalone in the kafka-init image; load it from its path. Dataclasses
# look their module up in sys.modules, so it must be registered before it executes.
spec = importlib.util.spec_from_file_location("apply_topics", SCRIPT)
apply_topics = importlib.util.module_from_spec(spec)
sys.modules["apply_topics"] = apply_topics
spec.loader.exec_module(apply_topics)

BOOTSTRAP = "kafka-1:29092"

DECLARATIONS = """
defaults:
  partitions: 6
  replication_factor: 3
  config:
    min.insync.replicas: 2
topics:
  - name: orders.v1
    config:
      retention.ms: 1000
  - name: small.v1
    partitions: 2
    replication_factor: 1
"""


def test_defaults_apply_to_every_topic_and_can_be_overridden():
    orders, small = apply_topics.parse_topics(DECLARATIONS)
    assert (orders.partitions, orders.replication_factor) == (6, 3)
    assert orders.config == {"min.insync.replicas": "2", "retention.ms": "1000"}
    assert (small.partitions, small.replication_factor) == (2, 1)
    assert small.config == {"min.insync.replicas": "2"}


def test_duplicate_declarations_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        apply_topics.parse_topics("topics:\n  - name: a\n  - name: a\n")


def test_missing_topic_is_created_with_its_settings():
    topics = apply_topics.parse_topics(DECLARATIONS)
    plan = apply_topics.plan(topics, existing={}, bootstrap=BOOTSTRAP)
    create = plan.commands[0]
    assert "--create" in create
    assert "--if-not-exists" in create
    assert create[create.index("--topic") + 1] == "orders.v1"
    assert create[create.index("--partitions") + 1] == "6"
    assert create[create.index("--replication-factor") + 1] == "3"
    assert "retention.ms=1000" in create
    assert plan.errors == []


def test_existing_topic_only_gets_its_configs_reapplied():
    topics = apply_topics.parse_topics(DECLARATIONS)[:1]
    plan = apply_topics.plan(topics, existing={"orders.v1": 6}, bootstrap=BOOTSTRAP)
    assert len(plan.commands) == 1
    command = plan.commands[0]
    assert "--add-config" in command
    assert command[command.index("--add-config") + 1] == "min.insync.replicas=2,retention.ms=1000"


def test_partitions_can_grow():
    topics = apply_topics.parse_topics(DECLARATIONS)[:1]
    plan = apply_topics.plan(topics, existing={"orders.v1": 3}, bootstrap=BOOTSTRAP)
    alter = plan.commands[0]
    assert "--alter" in alter
    assert alter[alter.index("--partitions") + 1] == "6"


def test_partitions_cannot_shrink():
    topics = apply_topics.parse_topics(DECLARATIONS)[:1]
    plan = apply_topics.plan(topics, existing={"orders.v1": 12}, bootstrap=BOOTSTRAP)
    assert plan.errors == [
        "orders.v1: declared 6 partitions but the topic has 12; Kafka cannot reduce partitions"
    ]


def test_describe_output_is_parsed_into_partition_counts():
    output = (
        "Topic: a.v1\tTopicId: x\tPartitionCount: 6\tReplicationFactor: 3\tConfigs: k=v\n"
        "\tTopic: a.v1\tPartition: 0\tLeader: 1\tReplicas: 1,2,3\tIsr: 1,2,3\n"
        "Topic: b.v1\tTopicId: y\tPartitionCount: 3\tReplicationFactor: 3\tConfigs: \n"
    )
    assert apply_topics.parse_describe(output) == {"a.v1": 6, "b.v1": 3}


def test_repository_declarations_are_valid():
    topics = apply_topics.parse_topics(TOPICS_FILE.read_text(encoding="utf-8"))
    assert topics
    for topic in topics:
        assert topic.name.startswith("sentinel.")
        assert topic.name.rsplit(".", 1)[-1].startswith("v")
        assert topic.replication_factor == 3
        assert topic.config["min.insync.replicas"] == "2"
