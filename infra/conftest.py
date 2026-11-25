"""Helpers for integration tests that run against the local compose stack.

Start the stack first (`make up PROFILE=core`), then run `make test-integration`.
"""

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest

COMPOSE_DIR = Path(__file__).resolve().parent / "compose"
COMPOSE_FILE = COMPOSE_DIR / "docker-compose.yml"
ENV_FILE = COMPOSE_DIR / ".env"
COMPOSE = [
    "docker", "compose",
    "--project-directory", str(COMPOSE_DIR), "-f", str(COMPOSE_FILE),
    "--profile", "all",
]  # fmt: skip

Compose = Callable[..., subprocess.CompletedProcess[str]]
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


def run_compose(
    *args: str, stdin: str | None = None, timeout_s: float = 120
) -> subprocess.CompletedProcess[str]:
    """Runs `docker compose <args>` on the local stack; the caller checks the return code."""
    return subprocess.run(
        [*COMPOSE, *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


def wait_until_ready(timeout_s: float = 240) -> None:
    """Blocks until every service is ready again, with the rules of wait-until-ready.sh.

    Long-running services must be healthy (or running without a healthcheck); one-shot
    services must have exited with code 0.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        listing = run_compose(
            "ps", "--all", "--format", "{{.Service}}|{{.State}}|{{.Health}}|{{.ExitCode}}"
        ).stdout
        pending = []
        for line in filter(None, listing.splitlines()):
            service, state, health, exit_code = line.split("|")
            if state == "exited" and exit_code != "0":
                raise RuntimeError(f"{service} exited with code {exit_code}")
            if (state == "running" and health not in ("", "healthy")) or state not in (
                "running",
                "exited",
            ):
                pending.append(f"{service} ({health or state})")
        if not pending:
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f"not ready after {timeout_s}s: {', '.join(pending)}")
        time.sleep(3)


@pytest.fixture(scope="session")
def env() -> dict[str, str]:
    if not ENV_FILE.exists():
        pytest.fail(f"{ENV_FILE} is missing: copy .env.example to .env, then run make up")
    return read_env_file(ENV_FILE)


@pytest.fixture(scope="session")
def compose() -> Compose:
    return run_compose


@pytest.fixture(scope="session")
def wait_ready() -> Callable[..., None]:
    return wait_until_ready


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
        args = ["exec", "-T"]
        if password is not None:
            # A password is only checked over TCP, so connect to localhost inside the container.
            args += ["-e", f"PGPASSWORD={password}"]
        args += [service, "psql", "--no-psqlrc", "-v", "ON_ERROR_STOP=1", "-qtA"]
        if password is not None:
            args += ["-h", "localhost"]
        args += ["-U", user, "-d", database]
        for statement in [sql] if isinstance(sql, str) else sql:
            args += ["-c", statement]
        result = run_compose(*args)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    return run
