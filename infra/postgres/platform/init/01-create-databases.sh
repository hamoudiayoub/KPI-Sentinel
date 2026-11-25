#!/usr/bin/env bash
# Creates one database per platform service, each owned by its own login role.
# Runs once, from the official image entrypoint, when the data volume is empty.
# Passwords come from the container environment (see infra/compose/.env.example).
set -euo pipefail

create_database() {
  local name="$1"
  local password="$2"
  # psql variables (:"name" for identifiers, :'password' for literals) quote the
  # values safely; nothing is concatenated into the SQL text.
  psql --no-psqlrc -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname postgres \
    -v name="$name" -v password="$password" <<-'SQL'
	CREATE ROLE :"name" LOGIN PASSWORD :'password';
	CREATE DATABASE :"name" OWNER :"name";
	-- Only the owner (and the superuser) may connect: services stay isolated.
	REVOKE CONNECT ON DATABASE :"name" FROM PUBLIC;
	SQL
  echo "created database and role: $name"
}

create_database platform "$PLATFORM_DB_PASSWORD"
create_database keycloak "$KEYCLOAK_DB_PASSWORD"
create_database nessie "$NESSIE_DB_PASSWORD"
create_database dagster "$DAGSTER_DB_PASSWORD"
