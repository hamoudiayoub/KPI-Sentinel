"""Checks the databases of the `core` profile once the stack is up."""

import pytest

pytestmark = pytest.mark.integration

PLATFORM_DATABASES = {
    "platform": "PLATFORM_DB_PASSWORD",
    "keycloak": "KEYCLOAK_DB_PASSWORD",
    "nessie": "NESSIE_DB_PASSWORD",
    "dagster": "DAGSTER_DB_PASSWORD",
}


def test_source_database_uses_logical_replication(psql):
    assert psql("postgres-source", "SHOW wal_level;") == "logical"


def test_source_database_allows_replication_slots(psql):
    assert int(psql("postgres-source", "SHOW max_replication_slots;")) >= 4
    assert int(psql("postgres-source", "SHOW max_wal_senders;")) >= 4


def test_platform_databases_exist_with_their_own_owner(psql):
    rows = psql(
        "postgres-platform",
        "SELECT d.datname || ':' || r.rolname FROM pg_database d "
        "JOIN pg_roles r ON r.oid = d.datdba ORDER BY 1;",
    ).splitlines()
    owners = dict(row.split(":", 1) for row in rows)
    for name in PLATFORM_DATABASES:
        assert owners.get(name) == name


@pytest.mark.parametrize("name", sorted(PLATFORM_DATABASES))
def test_each_service_role_can_log_into_its_database(psql, env, name):
    password = env[PLATFORM_DATABASES[name]]
    result = psql(
        "postgres-platform", "SELECT current_user;", user=name, database=name, password=password
    )
    assert result == name


def test_a_service_role_cannot_connect_to_another_service_database(psql, env):
    with pytest.raises(RuntimeError, match="permission denied"):
        psql(
            "postgres-platform",
            "SELECT 1;",
            user="platform",
            database="keycloak",
            password=env["PLATFORM_DB_PASSWORD"],
        )
