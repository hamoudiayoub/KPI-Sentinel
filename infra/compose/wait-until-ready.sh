#!/usr/bin/env bash
# Waits until every service of the selected profiles is ready, or fails after a timeout.
#
# Ready means: a long-running service is healthy (or running, when it has no healthcheck),
# and a one-shot service (migrations, topic creation) has exited with code 0.
# `docker compose up --wait` cannot express the second case, hence this script.
#
# Usage: wait-until-ready.sh <timeout-seconds> <docker compose command and options...>
set -euo pipefail

timeout_s="$1"
shift
compose=("$@")
deadline=$(( $(date +%s) + timeout_s ))

while true; do
  pending=()
  while IFS='|' read -r service state health exit_code; do
    [ -z "$service" ] && continue
    case "$state" in
      running)
        if [ -n "$health" ] && [ "$health" != "healthy" ]; then pending+=("$service ($health)"); fi
        ;;
      exited)
        if [ "$exit_code" != "0" ]; then
          echo "Service $service exited with code $exit_code. See: make logs S=$service" >&2
          exit 1
        fi
        ;;
      *)
        pending+=("$service ($state)")
        ;;
    esac
  done < <("${compose[@]}" ps --all --format '{{.Service}}|{{.State}}|{{.Health}}|{{.ExitCode}}')

  if [ "${#pending[@]}" -eq 0 ]; then
    echo "All services are ready."
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "Timed out after ${timeout_s}s. Not ready: ${pending[*]}" >&2
    exit 1
  fi
  sleep 3
done
