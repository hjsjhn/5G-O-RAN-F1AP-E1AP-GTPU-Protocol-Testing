#!/usr/bin/env bash
# Start the O-RAN test environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/docker/compose"

echo "Starting O-RAN test environment (CU-DU split + Open5GS)..."

docker compose \
  -f "$COMPOSE_DIR/docker-compose.yml" \
  -f "$COMPOSE_DIR/docker-compose.split.yml" \
  up -d

echo ""
echo "Waiting for services to become healthy..."
echo "  5gc:    AMF/SMF/UPF core network"
echo "  cu-cp:  CU Control Plane (NGAP + E1AP + F1AP)"
echo "  cu-up:  CU User Plane (F1-U + N3)"
echo "  du:     DU with ZMQ RF frontend"
echo ""
echo "Check status:  $SCRIPT_DIR/check_env.sh"
echo "View logs:     docker compose -f $COMPOSE_DIR/docker-compose.yml -f $COMPOSE_DIR/docker-compose.split.yml logs -f"
echo "Capture pcaps: docker cp srsran_cu_cp:/tmp/cu_cp_f1ap.pcap captures/raw/"
