#!/usr/bin/env bash
# Run srsUE 5G-SA over ZMQ against the active srsRAN DU.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/docker/compose/.env"
COMPOSE_MAIN="$PROJECT_ROOT/docker/compose/docker-compose.yml"
COMPOSE_SPLIT="$PROJECT_ROOT/docker/compose/docker-compose.split.yml"
SRSLTE_DIR="$PROJECT_ROOT/docker/open5gs-5gc/srslte"
IMAGE=srsue-5g-zmq:local
CONTAINER=srsue_5g_zmq
DOCKERFILE_DIR="$PROJECT_ROOT/docker/srsue-5g"
RAN_NETWORK_NAME="${RAN_NETWORK_NAME:-compose_ran}"

usage() {
  cat <<EOF
Usage: $0 [run|start|debug|down|logs|check|build]

Commands:
  run    Build image if needed, start srsUE over DU ZMQ, and verify attach/session logs.
  start  Build/provision/start srsUE over DU ZMQ, then leave it running for diagnostics.
  debug  Print runtime config, threads, sockets, DU ZMQ state, and recent logs.
  build  Build the local srsUE 5G ZMQ image.
  check  Verify an already-running srsUE container.
  logs   Show srsUE logs.
  down   Remove the srsUE smoke-test container.
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

  SRS_UE_IP="${SRS_UE_IP:-10.53.1.7}"
  SRS_GNB_IP="${SRS_GNB_IP:-${DU_IP:-10.53.1.6}}"
  SRSUE_RADIO_MODE="${SRSUE_RADIO_MODE:-multi}"
  SRSUE_TIME_ADV_NSAMPLES="${SRSUE_TIME_ADV_NSAMPLES:-0}"
  SRS_ZMQ_PRB="${SRS_ZMQ_PRB:-52}"
  SRS_ZMQ_SRATE_HZ="${SRS_ZMQ_SRATE_HZ:-11.52e6}"
  SRS_ZMQ_SSB_ARFCN="${SRS_ZMQ_SSB_ARFCN:-367930}"
  SRSUE_RECREATE_DU="${SRSUE_RECREATE_DU:-1}"

  : "${MCC:?missing MCC}"
  : "${MNC:?missing MNC}"
  : "${TAC:?missing TAC}"
  : "${DU_IP:?missing DU_IP}"
  : "${UE1_IMSI:?missing UE1_IMSI}"
  : "${UE1_KI:?missing UE1_KI}"
  : "${UE1_OP:?missing UE1_OP}"
}

build_image() {
  if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    return 0
  fi
  docker build -t "$IMAGE" "$DOCKERFILE_DIR"
}

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" == "true" ]]
}

remove_container() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

stop_ueransim_smoke() {
  "$SCRIPT_DIR/run_ueransim_smoke.sh" down >/dev/null 2>&1 || true
}

recreate_du() {
  if [[ "$SRSUE_RECREATE_DU" != "1" ]]; then
    return 0
  fi

  docker compose \
    -f "$COMPOSE_MAIN" \
    -f "$COMPOSE_SPLIT" \
    --env-file "$ENV_FILE" \
    up -d --no-deps --force-recreate du >/dev/null

  for _ in $(seq 1 60); do
    if "$SCRIPT_DIR/check_core_ready.sh" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  "$SCRIPT_DIR/check_core_ready.sh"
}

run_ue() {
  docker run -d \
    --name "$CONTAINER" \
    --network "$RAN_NETWORK_NAME" \
    --ip "$SRS_UE_IP" \
    --privileged \
    --cap-add NET_ADMIN \
    --env-file "$ENV_FILE" \
    -e SRS_UE_IP="$SRS_UE_IP" \
    -e SRS_GNB_IP="$SRS_GNB_IP" \
    -e SRSUE_TIME_ADV_NSAMPLES="$SRSUE_TIME_ADV_NSAMPLES" \
    -e SRS_ZMQ_PRB="$SRS_ZMQ_PRB" \
    -e SRS_ZMQ_SRATE_HZ="$SRS_ZMQ_SRATE_HZ" \
    -e SRS_ZMQ_SSB_ARFCN="$SRS_ZMQ_SSB_ARFCN" \
    -v "$SRSLTE_DIR:/mnt/srslte" \
    "$IMAGE" /bin/bash -lc '
      set -e
      mkdir -p /etc/srsran
      cp /mnt/srslte/ue_5g_zmq.conf /etc/srsran/ue.conf
      sed -i "s|UE1_KI|${UE1_KI}|g" /etc/srsran/ue.conf
      sed -i "s|UE1_OP|${UE1_OP}|g" /etc/srsran/ue.conf
      sed -i "s|UE1_IMSI|${UE1_IMSI}|g" /etc/srsran/ue.conf
      sed -i "s|SRS_UE_IP|${SRS_UE_IP}|g" /etc/srsran/ue.conf
      sed -i "s|SRS_GNB_IP|${SRS_GNB_IP}|g" /etc/srsran/ue.conf
      sed -i "s|srate = 23.04e6|srate = ${SRS_ZMQ_SRATE_HZ}|g" /etc/srsran/ue.conf
      sed -i "s|base_srate=23.04e6|base_srate=${SRS_ZMQ_SRATE_HZ}|g" /etc/srsran/ue.conf
      sed -i "s|max_nof_prb = 106|max_nof_prb = ${SRS_ZMQ_PRB}|g" /etc/srsran/ue.conf
      sed -i "s|nof_prb = 106|nof_prb = ${SRS_ZMQ_PRB}|g" /etc/srsran/ue.conf
      sed -i "s|ssb_nr_arfcn = 368410|ssb_nr_arfcn = ${SRS_ZMQ_SSB_ARFCN}|g" /etc/srsran/ue.conf
      sed -i "s|filename = /mnt/srslte/ue.log|filename = stdout|g" /etc/srsran/ue.conf
      sed -i "s|all_level = warning|all_level = info|g" /etc/srsran/ue.conf
      sed -i "s|phy_lib_level = none|phy_lib_level = warning|g" /etc/srsran/ue.conf
      exec /usr/local/bin/srsue /etc/srsran/ue.conf --ue.radio="${SRSUE_RADIO_MODE}" --ue.phy=nr --rat.nr.scs=15 --rat.nr.ssb_scs=15 --rf.time_adv_nsamples="${SRSUE_TIME_ADV_NSAMPLES}"
    ' >/dev/null
}

wait_for_log() {
  local pattern="$1"
  local seconds="${2:-90}"
  local logs

  for _ in $(seq 1 "$seconds"); do
    logs="$(docker logs --tail 4000 "$CONTAINER" 2>&1 || true)"
    if grep -Eiq "$pattern" <<<"$logs"; then
      return 0
    fi
    if ! container_running "$CONTAINER"; then
      echo "$CONTAINER exited before '$pattern' appeared." >&2
      docker logs --tail 300 "$CONTAINER" >&2 || true
      return 1
    fi
    sleep 1
  done

  echo "Timed out waiting for '$pattern' in $CONTAINER logs." >&2
  docker logs --tail 300 "$CONTAINER" >&2 || true
  return 1
}

wait_for_tun() {
  local seconds="${1:-120}"

  for _ in $(seq 1 "$seconds"); do
    if docker exec "$CONTAINER" sh -lc 'ip -4 addr show tun_srsue 2>/dev/null | grep -q "inet "'; then
      return 0
    fi
    if ! container_running "$CONTAINER"; then
      echo "$CONTAINER exited before tun_srsue received an IPv4 address." >&2
      docker logs --tail 300 "$CONTAINER" >&2 || true
      return 1
    fi
    sleep 1
  done

  echo "Timed out waiting for tun_srsue IPv4 address in $CONTAINER." >&2
  docker logs --tail 300 "$CONTAINER" >&2 || true
  return 1
}

check_smoke() {
  container_running "$CONTAINER"
  wait_for_tun 120
  echo "OK: srsUE reached the DU over ZMQ and produced attach/session progress logs."
}

start_smoke() {
  load_env
  "$SCRIPT_DIR/check_core_ready.sh" >/dev/null
  "$SCRIPT_DIR/provision_subscriber.sh" >/dev/null
  build_image
  stop_ueransim_smoke
  remove_container
  recreate_du
  run_ue
  echo "Started $CONTAINER."
}

debug_smoke() {
  echo "== generated UE config =="
  docker exec "$CONTAINER" sh -lc "sed -n '1,120p' /etc/srsran/ue.conf; sed -n '320,385p' /etc/srsran/ue.conf" 2>&1 || true
  echo
  echo "== srsUE process tree =="
  docker exec "$CONTAINER" sh -lc 'ps -ef; ps -T -p 1 -o pid,tid,stat,pcpu,comm,wchan:40 2>/dev/null || true' 2>&1 || true
  echo
  echo "== srsUE ZMQ sockets =="
  docker exec "$CONTAINER" sh -lc 'ss -tanpi | grep -E "2000|2001" || true' 2>&1 || true
  echo
  echo "== srsUE tun =="
  docker exec "$CONTAINER" sh -lc 'ip -4 addr show tun_srsue 2>/dev/null || true' 2>&1 || true
  echo
  echo "== DU ZMQ sockets =="
  docker exec srsran_du sh -lc 'ss -tanpi | grep -E "2000|2001" || true' 2>&1 || true
  echo
  echo "== DU recent ZMQ log =="
  docker exec srsran_du sh -lc 'tail -120 /tmp/du.log 2>/dev/null | grep -E "zmq|RACH|UE|F1|error|warn" || true' 2>&1 || true
  echo
  echo "== srsUE recent logs =="
  show_logs
}

show_logs() {
  docker logs --tail 220 "$CONTAINER" 2>&1 || true
}

cmd="${1:-run}"
case "$cmd" in
  run)
    start_smoke
    check_smoke
    ;;
  start)
    start_smoke
    ;;
  debug)
    debug_smoke
    ;;
  build)
    build_image
    ;;
  check)
    check_smoke
    ;;
  logs)
    show_logs
    ;;
  down)
    remove_container
    echo "Removed $CONTAINER."
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
