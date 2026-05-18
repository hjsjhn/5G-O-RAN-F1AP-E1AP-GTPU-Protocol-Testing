#!/usr/bin/env bash
# Full reset: stop, remove volumes, restart clean
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/docker/compose"

echo "Stopping and removing all containers, volumes, and networks..."
docker compose \
  -f "$COMPOSE_DIR/docker-compose.yml" \
  -f "$COMPOSE_DIR/docker-compose.split.yml" \
  down -v --remove-orphans 2>/dev/null || true

echo "Starting fresh environment..."
"$SCRIPT_DIR/start_env.sh"
