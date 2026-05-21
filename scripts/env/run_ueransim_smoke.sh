#!/usr/bin/env bash
# Run a UERANSIM 5G Core smoke test against the Open5GS core.
#
# This verifies UE registration and PDU Session on the 5G Core. It does not
# exercise the srsRAN CU-DU/O-RAN path; use it as a core-health smoke test.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/docker/compose/.env"
UERANSIM_DIR="$PROJECT_ROOT/docker/open5gs-5gc/ueransim"
DOCKER_NETWORK_NAME="${DOCKER_NETWORK_NAME:-compose_5gc}"
GNB_CONTAINER=nr_gnb
UE_CONTAINER=nr_ue
IMAGE=docker_ueransim:latest

usage() {
  cat <<EOF
Usage: $0 [run|down|logs|check]

Commands:
  run    Build image if needed, start UERANSIM gNB + UE, and verify registration/PDU session.
  check  Verify an already-running UERANSIM smoke test.
  logs   Show gNB and UE logs.
  down   Remove UERANSIM smoke-test containers.
EOF
}

load_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing $ENV_FILE. Run scripts/env/start_env.sh first." >&2
    exit 1
  fi

  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a

  : "${MCC:?missing MCC}"
  : "${MNC:?missing MNC}"
  : "${TAC:?missing TAC}"
  : "${AMF_IP:?missing AMF_IP}"
  : "${NR_GNB_IP:?missing NR_GNB_IP}"
  : "${NR_UE_IP:?missing NR_UE_IP}"
  : "${UE1_IMSI:?missing UE1_IMSI}"
  : "${UE1_KI:?missing UE1_KI}"
  : "${UE1_OP:?missing UE1_OP}"
  : "${UE1_AMF:?missing UE1_AMF}"
  : "${UE1_IMEI:?missing UE1_IMEI}"
  : "${UE1_IMEISV:?missing UE1_IMEISV}"
}

require_core_ready() {
  "$SCRIPT_DIR/check_core_ready.sh" >/dev/null
  "$SCRIPT_DIR/provision_subscriber.sh" >/dev/null
}

build_image() {
  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    if [[ ! -d "$UERANSIM_DIR" ]]; then
      echo "Missing $UERANSIM_DIR. Ensure docker/open5gs-5gc is cloned before running this smoke test." >&2
      exit 1
    fi
    docker build -t "$IMAGE" "$UERANSIM_DIR"
  fi
}

remove_containers() {
  docker rm -f "$UE_CONTAINER" "$GNB_CONTAINER" >/dev/null 2>&1 || true
}

run_gnb() {
  docker run -d \
    --name "$GNB_CONTAINER" \
    --network "$DOCKER_NETWORK_NAME" \
    --ip "$NR_GNB_IP" \
    --privileged \
    --cap-add NET_ADMIN \
    --env-file "$ENV_FILE" \
    -e COMPONENT_NAME=ueransim-gnb \
    -v "$UERANSIM_DIR:/mnt/ueransim" \
    "$IMAGE" /bin/bash -lc '
      set -e
      cp /mnt/ueransim/${COMPONENT_NAME}.yaml /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|MNC|${MNC}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|MCC|${MCC}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|TAC|${TAC}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|NR_GNB_IP|${NR_GNB_IP}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|AMF_IP|${AMF_IP}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      exec ./nr-gnb -c ../config/${COMPONENT_NAME}.yaml
    ' >/dev/null
}

run_ue() {
  docker run -d \
    --name "$UE_CONTAINER" \
    --network "$DOCKER_NETWORK_NAME" \
    --ip "$NR_UE_IP" \
    --privileged \
    --cap-add NET_ADMIN \
    --env-file "$ENV_FILE" \
    -e COMPONENT_NAME=ueransim-ue \
    -v "$UERANSIM_DIR:/mnt/ueransim" \
    "$IMAGE" /bin/bash -lc '
      set -e
      cp /mnt/ueransim/${COMPONENT_NAME}.yaml /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|MNC|${MNC}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|MCC|${MCC}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|UE1_KI|${UE1_KI}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|UE1_OP|${UE1_OP}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|UE1_AMF|${UE1_AMF}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|UE1_IMEISV|${UE1_IMEISV}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|UE1_IMEI|${UE1_IMEI}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|UE1_IMSI|${UE1_IMSI}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      sed -i "s|NR_GNB_IP|${NR_GNB_IP}|g" /UERANSIM/config/${COMPONENT_NAME}.yaml
      exec ./nr-ue -c ../config/${COMPONENT_NAME}.yaml
    ' >/dev/null
}

wait_for_log() {
  local container="$1"
  local pattern="$2"
  local seconds="${3:-60}"

  for _ in $(seq 1 "$seconds"); do
    if docker logs "$container" 2>&1 | grep -Eiq "$pattern"; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for '$pattern' in $container logs." >&2
  docker logs "$container" >&2 || true
  return 1
}

check_smoke() {
  docker ps --format '{{.Names}}' | grep -q "^${GNB_CONTAINER}$"
  docker ps --format '{{.Names}}' | grep -q "^${UE_CONTAINER}$"
  wait_for_log "$GNB_CONTAINER" 'NG Setup procedure is successful|NG Setup complete|Connection setup' 20
  wait_for_log "$UE_CONTAINER" 'Registration is successful|registered to the network' 60
  wait_for_log "$UE_CONTAINER" 'PDU Session establishment is successful|PDU session.*established' 60
  echo "OK: UERANSIM UE registered and established a PDU Session."
}

show_logs() {
  echo "=== $GNB_CONTAINER ==="
  docker logs --tail 120 "$GNB_CONTAINER" 2>&1 || true
  echo ""
  echo "=== $UE_CONTAINER ==="
  docker logs --tail 160 "$UE_CONTAINER" 2>&1 || true
}

cmd="${1:-run}"
case "$cmd" in
  run)
    load_env
    require_core_ready
    build_image
    remove_containers
    run_gnb
    sleep 3
    run_ue
    check_smoke
    ;;
  check)
    check_smoke
    ;;
  logs)
    show_logs
    ;;
  down)
    remove_containers
    echo "Removed UERANSIM smoke-test containers."
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
