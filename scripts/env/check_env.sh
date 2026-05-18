#!/usr/bin/env bash
# Check the status of O-RAN test environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/docker/compose"

echo "=== Container Status ==="
docker compose \
  -f "$COMPOSE_DIR/docker-compose.yml" \
  -f "$COMPOSE_DIR/docker-compose.split.yml" \
  ps

echo ""
echo "=== Network Connectivity ==="
for container in srsran_cu_cp srsran_cu_up srsran_du open5gs_5gc; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    echo "  $container: $(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$container")"
  fi
done

echo ""
echo "=== SCTP Ports (F1AP/E1AP/NGAP) ==="
for container in srsran_cu_cp srsran_cu_up srsran_du; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    echo "  $container:"
    docker exec "$container" ss -l -A sctp 2>/dev/null || echo "    (unable to query)"
  fi
done

echo ""
echo "=== Recent Logs (last 5 lines per service) ==="
for svc in 5gc cu-cp cu-up du; do
  echo "  [$svc]"
  docker compose \
    -f "$COMPOSE_DIR/docker-compose.yml" \
    -f "$COMPOSE_DIR/docker-compose.split.yml" \
    logs --tail 5 "$svc" 2>/dev/null | sed 's/^/    /'
done
