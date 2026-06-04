#!/usr/bin/env bash
# Strictly restore and verify the default baseline environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_MAIN="$PROJECT_ROOT/docker/compose/docker-compose.yml"
COMPOSE_SPLIT="$PROJECT_ROOT/docker/compose/docker-compose.split.yml"
TIMEOUT="${RESTORE_BASELINE_TIMEOUT:-120}"

remove_if_present() {
  local container="$1"
  if docker inspect "$container" >/dev/null 2>&1; then
    docker rm -f "$container" >/dev/null
  fi
}

cd "$PROJECT_ROOT"
echo "Restoring default baseline..."
remove_if_present srsue_5g_zmq
remove_if_present nr_ue
remove_if_present nr_gnb

docker compose -f "$COMPOSE_MAIN" -f "$COMPOSE_SPLIT" \
  up -d --force-recreate cu-cp cu-up du >/dev/null

for _ in $(seq 1 "$TIMEOUT"); do
  if ./scripts/env/check_core_ready.sh >/dev/null 2>&1; then
    if [[ "${RESTORE_BASELINE_TEST_FORCE_FAILURE:-0}" == "1" ]]; then
      echo "TEST-ONLY: forcing restore failure after a healthy restoration." >&2
      exit 97
    fi
    echo "OK: default baseline restored and healthy."
    exit 0
  fi
  sleep 1
done

echo "ERROR: default baseline did not become healthy within ${TIMEOUT}s." >&2
./scripts/env/check_core_ready.sh >&2
exit 1
