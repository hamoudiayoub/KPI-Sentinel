"""Helpers for integration tests that run against the local compose stack.

Start the stack first (`make up PROFILE=core`), then run `make test-integration`.
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

COMPOSE_DIR = Path(__file__).resolve().parent / "compose"
COMPOSE_FILE = COMPOSE_DIR / "docker-compose.yml"
ENV_FILE = COMPOSE_DIR / ".env"

Psql = Callable[..., str]


def read_env_file(path: Path) -> dict[str, str]:
    """Parses the KEY=VALUE lines of a .env file, ignoring comments and blank lines."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


@pytest.fixture(scope="session")
def env() -> dict[str, str]:
    if not ENV_FILE.exists():
        pytest.fail(f"{ENV_FILE} is missing: copy .env.example to .env, then run make up")
    return read_env_file(ENV_FILE)


@pytest.fixture(scope="session")
def psql() -> Psql:
    """Runs SQL with psql inside a service container and returns its output.

    `sql` is one statement, or a list of statements run in order in the same session
    (useful for BEGIN ... ROLLBACK). Only query results are printed, not command tags.
    """

    def run(
        service: str,
        sql: str | list[str],
        *,
        user: str = "postgres",
        database: str = "postgres",
        password: str | None = None,
    ) -> str:
        command = [
            "docker",
            "compose",
            "--project-directory",
            str(COMPOSE_DIR),
            "-f",
            str(COMPOSE_FILE),
            "exec",
            "-T",
        ]
        if password is not None:
            # A password is only checked over TCP, so connect to localhost inside the container.
            command += ["-e", f"PGPASSWORD={password}"]
        command += [service, "psql", "--no-psqlrc", "-v", "ON_ERROR_STOP=1", "-qtA"]
        if password is not None:
            command += ["-h", "localhost"]
        command += ["-U", user, "-d", database]
        for statement in [sql] if isinstance(sql, str) else sql:
            command += ["-c", statement]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    return run
