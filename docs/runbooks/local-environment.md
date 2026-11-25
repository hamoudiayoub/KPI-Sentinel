# Runbook — Local environment

- **Service**: Docker Compose stack (`infra/compose/`)
- **Severity**: minor (development only)

## Start

```bash
cp infra/compose/.env.example infra/compose/.env   # once per clone
make up PROFILE=core                               # or PROFILE="core lake", or PROFILE=all
make ps
```

`make up` returns once every started service reports `healthy`, or fails after 180 s. Profiles:

| Profile | Services |
|---|---|
| `core` | `postgres-source` (ERP, `atlas` database), `postgres-platform` (`platform`, `keycloak`, `nessie`, `dagster` databases) |
| `lake`, `platform`, `obs` | Added with their components |
| `all` | Every service |

Connect to a database:

```bash
make psql-source                      # interactive psql on the ERP database
make psql-source <<< "SELECT 1;"      # one statement
make psql-platform
```

From the host, use `127.0.0.1` and the ports from `infra/compose/.env`.

## Stop

```bash
make down          # stops every service; data volumes are kept
make logs          # follow all logs
make logs S=postgres-source
```

## Reset

```bash
make reset
```

`make reset` asks for confirmation, then stops the stack and deletes its data volumes. Only the answer `yes` deletes anything. Use it when the data is corrupt, or to re-run the database init scripts: they only run when a volume is created, so changing a password in `.env` has no effect on an existing volume.

## Verify

```bash
make test-integration   # wal_level, platform databases, role isolation
```

## Common problems

### A port is already in use

Symptom: `ports are not available` or `bind: address already in use` during `make up`.

1. Find the owner: `netstat -ano | findstr :5432` on Windows, `lsof -i :5432` on Linux and macOS.
2. Either stop that process (for example a Postgres installed on the host), or change the port in `infra/compose/.env`, such as `POSTGRES_SOURCE_PORT=15432`.
3. `make down && make up PROFILE=core`.

### Docker runs out of memory

Symptoms: containers restart in a loop, `make up` times out, `docker stats` shows services at their limit, or exit code 137 in `make logs`.

1. Check the memory available to Docker: `docker info --format '{{.MemTotal}}'`.
2. Allocate at least 10 GB in Docker Desktop (Settings → Resources), or in `.wslconfig` (`memory=10GB`) on Windows with WSL2, then restart Docker.
3. With less memory, run profiles two at a time: `core` + `lake`, then `core` + `platform`.

### A service stays unhealthy

1. `make ps` to see which one, then `make logs S=<service>`.
2. For a database that will not start after a version change, the volume was created by an incompatible version: `make reset`.

## Escalation and follow-up

Open an issue with the output of `make ps`, `docker info` and the relevant logs.
