#!/usr/bin/env bash
# Stop the O-RAN test environment and collect pcaps
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/docker/compose"
CAPTURE_DIR="$PROJECT_ROOT/captures/raw"

echo "Collecting pcap files from containers..."

mkdir -p "$CAPTURE_DIR"
for container in srsran_cu_cp srsran_cu_up srsran_du; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    echo "  Copying pcaps from $container..."
    docker cp "$container:/tmp/." "$CAPTURE_DIR/${container}_pcaps/" 2>/dev/null || true
  fi
done

echo "Collecting logs..."
LOG_DIR="$PROJECT_ROOT/logs/run_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

docker compose \
  -f "$COMPOSE_DIR/docker-compose.yml" \
  -f "$COMPOSE_DIR/docker-compose.split.yml" \
  logs --no-color > "$LOG_DIR/all.log" 2>/dev/null || true

for svc in 5gc cu-cp cu-up du; do
  docker compose \
    -f "$COMPOSE_DIR/docker-compose.yml" \
    -f "$COMPOSE_DIR/docker-compose.split.yml" \
    logs --no-color "$svc" > "$LOG_DIR/${svc}.log" 2>/dev/null || true
done

echo "Stopping environment..."
docker compose \
  -f "$COMPOSE_DIR/docker-compose.yml" \
  -f "$COMPOSE_DIR/docker-compose.split.yml" \
  down --remove-orphans

echo "Logs saved to: $LOG_DIR"
echo "Pcaps saved to: $CAPTURE_DIR"
