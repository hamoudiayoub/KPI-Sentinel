"""Applies the topic declarations of topics.yaml to the Kafka cluster, idempotently.

Missing topics are created, partitions are increased when the declaration asks for more,
and the declared configs are set on every run. Shrinking a topic is impossible in Kafka,
so a declaration with fewer partitions than the topic has is reported as an error.

The planning logic is pure (parse_topics, plan); only main() talks to the cluster, through
the official Kafka command-line tools.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

KAFKA_BIN = Path(os.environ.get("KAFKA_BIN", "/opt/kafka/bin"))


@dataclass(frozen=True)
class Topic:
    name: str
    partitions: int
    replication_factor: int
    config: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    commands: list[list[str]]
    errors: list[str]


def parse_topics(text: str) -> list[Topic]:
    """Reads the declarations, applying the defaults to every topic."""
    document = yaml.safe_load(text) or {}
    defaults = document.get("defaults", {})
    default_config = {k: str(v) for k, v in defaults.get("config", {}).items()}
    topics: list[Topic] = []
    for entry in document.get("topics", []):
        config = default_config | {k: str(v) for k, v in entry.get("config", {}).items()}
        topics.append(
            Topic(
                name=entry["name"],
                partitions=int(entry.get("partitions", defaults.get("partitions", 1))),
                replication_factor=int(
                    entry.get("replication_factor", defaults.get("replication_factor", 1))
                ),
                config=config,
            )
        )
    names = [t.name for t in topics]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"duplicate topic declarations: {', '.join(duplicates)}")
    return topics


def plan(topics: list[Topic], existing: dict[str, int], bootstrap: str) -> Plan:
    """Builds the CLI commands that bring the cluster to the declared state.

    `existing` maps each topic already in the cluster to its partition count.
    """
    commands: list[list[str]] = []
    errors: list[str] = []
    for topic in topics:
        current = existing.get(topic.name)
        if current is None:
            create = [
                str(KAFKA_BIN / "kafka-topics.sh"), "--bootstrap-server", bootstrap,
                "--create", "--if-not-exists", "--topic", topic.name,
                "--partitions", str(topic.partitions),
                "--replication-factor", str(topic.replication_factor),
            ]  # fmt: skip
            for key, value in sorted(topic.config.items()):
                create += ["--config", f"{key}={value}"]
            commands.append(create)
            continue
        if topic.partitions > current:
            commands.append(
                [
                    str(KAFKA_BIN / "kafka-topics.sh"),
                    "--bootstrap-server",
                    bootstrap,
                    "--alter",
                    "--topic",
                    topic.name,
                    "--partitions",
                    str(topic.partitions),
                ]
            )
        elif topic.partitions < current:
            errors.append(
                f"{topic.name}: declared {topic.partitions} partitions but the topic has "
                f"{current}; Kafka cannot reduce partitions"
            )
        if topic.config:
            settings = ",".join(f"{k}={v}" for k, v in sorted(topic.config.items()))
            commands.append(
                [
                    str(KAFKA_BIN / "kafka-configs.sh"),
                    "--bootstrap-server",
                    bootstrap,
                    "--alter",
                    "--entity-type",
                    "topics",
                    "--entity-name",
                    topic.name,
                    "--add-config",
                    settings,
                ]
            )
    return Plan(commands=commands, errors=errors)


def parse_describe(output: str) -> dict[str, int]:
    """Extracts the partition count of each topic from `kafka-topics.sh --describe`."""
    counts: dict[str, int] = {}
    for line in output.splitlines():
        if not line.startswith("Topic:") or "PartitionCount:" not in line:
            continue
        fields = dict(
            part.split(":", 1) for part in line.split("\t") if ":" in part and part.strip()
        )
        counts[fields["Topic"].strip()] = int(fields["PartitionCount"].strip())
    return counts


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)}\n{result.stderr.strip()}")
    return result.stdout


def describe_existing(bootstrap: str, attempts: int = 30, delay_s: float = 2.0) -> dict[str, int]:
    """Waits for the cluster to answer, then returns the existing topics."""
    command = [str(KAFKA_BIN / "kafka-topics.sh"), "--bootstrap-server", bootstrap, "--describe"]
    for attempt in range(1, attempts + 1):
        try:
            return parse_describe(run(command))
        except RuntimeError:
            if attempt == attempts:
                raise
            time.sleep(delay_s)
    return {}


def main() -> int:
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    topics_file = Path(os.environ.get("TOPICS_FILE", "/etc/kafka-init/topics.yaml"))
    topics = parse_topics(topics_file.read_text(encoding="utf-8"))
    actions = plan(topics, describe_existing(bootstrap), bootstrap)
    for error in actions.errors:
        print(f"error: {error}", file=sys.stderr)
    if actions.errors:
        return 1
    for command in actions.commands:
        run(command)
        print("applied:", " ".join(command[3:]))
    print(f"{len(topics)} topics declared, {len(actions.commands)} commands applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
