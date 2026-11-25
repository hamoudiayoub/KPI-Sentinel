"""Fixtures: a throwaway Postgres with the ERP migrations applied (Testcontainers).

Integration tests never touch the local compose stack: each test session gets its own
database, created from the same image and the same Flyway migrations.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from sentinel_gen.config import MarketConfig, load_config
from sentinel_gen.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "infra" / "postgres" / "source" / "migrations"
POSTGRES_IMAGE = "postgres:18.7-bookworm"


def migration_files() -> list[Path]:
    def version(path: Path) -> int:
        return int(re.match(r"V(\d+)__", path.name).group(1))

    return sorted(MIGRATIONS.glob("V*__*.sql"), key=version)


@pytest.fixture(scope="session")
def config() -> MarketConfig:
    return load_config()


@pytest.fixture(scope="session")
def postgres() -> Iterator[Settings]:
    """Starts Postgres, applies the migrations like Flyway does, yields connection settings."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        POSTGRES_IMAGE, username="postgres", password="test-only", dbname="atlas", driver=None
    ) as container:
        settings = Settings(
            db_host=container.get_container_host_ip(),
            db_port=int(container.get_exposed_port(5432)),
            db_name="atlas",
            db_user="postgres",
            db_password="test-only",
        )
        with psycopg.connect(settings.conninfo(), password="test-only", autocommit=True) as conn:
            conn.execute("CREATE SCHEMA erp")
            for path in migration_files():
                script = path.read_text(encoding="utf-8")
                conn.execute(script.replace("${debezium_password}", "test-only"))
        yield settings


@pytest.fixture
def conn(postgres: Settings) -> Iterator[psycopg.Connection]:
    with psycopg.connect(postgres.conninfo(), password="test-only") as connection:
        yield connection
