#!/usr/bin/env bash
# Control test: run monolithic srsRAN Project gNB + srsUE 5G-SA over ZMQ.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/docker/compose/.env"
SRSRAN_DIR="$PROJECT_ROOT/docker/open5gs-5gc/srsran"
SRSLTE_DIR="$PROJECT_ROOT/docker/open5gs-5gc/srslte"
GNB_IMAGE=srsran/gnb:local-arm64
UE_IMAGE=srsue-5g-zmq:local
GNB_CONTAINER=srsran_gnb_zmq_control
UE_CONTAINER=srsue_5g_zmq_control
GNB_DOCKERFILE="$PROJECT_ROOT/docker/Dockerfile.srsran"
GNB_CONTEXT="$PROJECT_ROOT/docker"
UE_DOCKERFILE_DIR="$PROJECT_ROOT/docker/srsue-5g"

usage() {
  cat <<EOF
Usage: $0 [run|start|debug|down|logs|check|build]

Commands:
  run    Build local images if needed, start control gNB + srsUE, and verify attach/session logs.
  start  Build/provision/start control gNB + srsUE, then leave containers running for diagnostics.
  debug  Print srsUE runtime config, threads, wait channels, sockets, and recent logs.
  build  Build local gNB and srsUE images.
  check  Verify already-running control containers.
  logs   Show control gNB and srsUE logs.
  down   Remove control containers.
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

  RAN_NETWORK_NAME="${RAN_NETWORK_NAME:-compose_ran}"
  SRS_CONTROL_GNB_IP="${SRS_CONTROL_GNB_IP:-10.53.1.8}"
  SRS_CONTROL_UE_IP="${SRS_CONTROL_UE_IP:-10.53.1.9}"
  SRSUE_RADIO_MODE="${SRSUE_RADIO_MODE:-multi}"
  SRS_CONTROL_BW_MHZ="${SRS_CONTROL_BW_MHZ:-10}"
  SRS_CONTROL_PRB="${SRS_CONTROL_PRB:-52}"
  SRS_CONTROL_SRATE_MHZ="${SRS_CONTROL_SRATE_MHZ:-11.52}"
  SRS_CONTROL_SRATE_HZ="${SRS_CONTROL_SRATE_HZ:-11.52e6}"
  SRS_CONTROL_CORESET0_INDEX="${SRS_CONTROL_CORESET0_INDEX:-0}"
  SRS_CONTROL_SSB_ARFCN="${SRS_CONTROL_SSB_ARFCN:-367930}"
  SRS_CONTROL_TIME_ALIGNMENT="${SRS_CONTROL_TIME_ALIGNMENT:-0}"
  SRSUE_TIME_ADV_NSAMPLES="${SRSUE_TIME_ADV_NSAMPLES:-0}"

  : "${MCC:?missing MCC}"
  : "${MNC:?missing MNC}"
  : "${TAC:?missing TAC}"
  : "${AMF_RAN_IP:?missing AMF_RAN_IP}"
  : "${UE1_IMSI:?missing UE1_IMSI}"
  : "${UE1_KI:?missing UE1_KI}"
  : "${UE1_OP:?missing UE1_OP}"
}

build_images() {
  if ! docker run --rm "$GNB_IMAGE" sh -lc 'command -v gnb' >/dev/null 2>&1; then
    docker build -t "$GNB_IMAGE" -f "$GNB_DOCKERFILE" "$GNB_CONTEXT"
  fi

  if ! docker image inspect "$UE_IMAGE" >/dev/null 2>&1; then
    docker build -t "$UE_IMAGE" "$UE_DOCKERFILE_DIR"
  fi
}

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" == "true" ]]
}

remove_containers() {
  docker rm -f "$UE_CONTAINER" "$GNB_CONTAINER" >/dev/null 2>&1 || true
}

stop_other_smoke_ues() {
  "$SCRIPT_DIR/run_ueransim_smoke.sh" down >/dev/null 2>&1 || true
  "$SCRIPT_DIR/run_srsue_zmq_smoke.sh" down >/dev/null 2>&1 || true
}

run_gnb() {
  docker run -d \
    --name "$GNB_CONTAINER" \
    --network "$RAN_NETWORK_NAME" \
    --ip "$SRS_CONTROL_GNB_IP" \
    --privileged \
    --cap-add SYS_NICE \
    --env-file "$ENV_FILE" \
    -e SRS_GNB_IP="$SRS_CONTROL_GNB_IP" \
    -e SRS_UE_IP="$SRS_CONTROL_UE_IP" \
    -e AMF_IP="$AMF_RAN_IP" \
    -e SRS_CONTROL_BW_MHZ="$SRS_CONTROL_BW_MHZ" \
    -e SRS_CONTROL_SRATE_MHZ="$SRS_CONTROL_SRATE_MHZ" \
    -e SRS_CONTROL_SRATE_HZ="$SRS_CONTROL_SRATE_HZ" \
    -e SRS_CONTROL_CORESET0_INDEX="$SRS_CONTROL_CORESET0_INDEX" \
    -e SRS_CONTROL_SSB_ARFCN="$SRS_CONTROL_SSB_ARFCN" \
    -e SRS_CONTROL_TIME_ALIGNMENT="$SRS_CONTROL_TIME_ALIGNMENT" \
    -v "$SRSRAN_DIR:/mnt/srsran" \
    "$GNB_IMAGE" /bin/bash -lc '
      set -e
      mkdir -p /etc/srsran
      cp /mnt/srsran/gnb_zmq.yml /etc/srsran/gnb.yml
      cp /mnt/srsran/qos.yml /etc/srsran/qos.yml
      sed -i "s|PLMN|${MCC}${MNC}|g" /etc/srsran/gnb.yml
      sed -i "s|AMF_IP|${AMF_IP}|g" /etc/srsran/gnb.yml
      sed -i "s|SRS_GNB_IP|${SRS_GNB_IP}|g" /etc/srsran/gnb.yml
      sed -i "s|SRS_UE_IP|${SRS_UE_IP}|g" /etc/srsran/gnb.yml
      sed -i "s|TAC|${TAC}|g" /etc/srsran/gnb.yml
      sed -i "s|channel_bandwidth_MHz: 20|channel_bandwidth_MHz: ${SRS_CONTROL_BW_MHZ}|g" /etc/srsran/gnb.yml
      sed -i "s|srate: 23.04|srate: ${SRS_CONTROL_SRATE_MHZ}|g" /etc/srsran/gnb.yml
      sed -i "s|base_srate=23.04e6|base_srate=${SRS_CONTROL_SRATE_HZ}|g" /etc/srsran/gnb.yml
      sed -i "s|coreset0_index: 13|coreset0_index: ${SRS_CONTROL_CORESET0_INDEX}|g" /etc/srsran/gnb.yml
      sed -i "/rx_gain:/a\\  time_alignment_calibration: ${SRS_CONTROL_TIME_ALIGNMENT}" /etc/srsran/gnb.yml
      sed -i "s|filename: /mnt/srsran/gnb.log|filename: stdout|g" /etc/srsran/gnb.yml
      sed -i "s|all_level: warning|all_level: info|g" /etc/srsran/gnb.yml
      exec gnb -c /etc/srsran/gnb.yml -c /etc/srsran/qos.yml
    ' >/dev/null
}

run_ue() {
  docker run -d \
    --name "$UE_CONTAINER" \
    --network "$RAN_NETWORK_NAME" \
    --ip "$SRS_CONTROL_UE_IP" \
    --privileged \
    --cap-add NET_ADMIN \
    --env-file "$ENV_FILE" \
    -e SRS_UE_IP="$SRS_CONTROL_UE_IP" \
    -e SRS_GNB_IP="$SRS_CONTROL_GNB_IP" \
    -e SRS_CONTROL_PRB="$SRS_CONTROL_PRB" \
    -e SRS_CONTROL_SRATE_HZ="$SRS_CONTROL_SRATE_HZ" \
    -e SRS_CONTROL_SSB_ARFCN="$SRS_CONTROL_SSB_ARFCN" \
    -e SRSUE_TIME_ADV_NSAMPLES="$SRSUE_TIME_ADV_NSAMPLES" \
    -v "$SRSLTE_DIR:/mnt/srslte" \
    "$UE_IMAGE" /bin/bash -lc '
      set -e
      mkdir -p /etc/srsran
      cp /mnt/srslte/ue_5g_zmq.conf /etc/srsran/ue.conf
      sed -i "s|UE1_KI|${UE1_KI}|g" /etc/srsran/ue.conf
      sed -i "s|UE1_OP|${UE1_OP}|g" /etc/srsran/ue.conf
      sed -i "s|UE1_IMSI|${UE1_IMSI}|g" /etc/srsran/ue.conf
      sed -i "s|SRS_UE_IP|${SRS_UE_IP}|g" /etc/srsran/ue.conf
      sed -i "s|SRS_GNB_IP|${SRS_GNB_IP}|g" /etc/srsran/ue.conf
      sed -i "s|srate = 23.04e6|srate = ${SRS_CONTROL_SRATE_HZ}|g" /etc/srsran/ue.conf
      sed -i "s|base_srate=23.04e6|base_srate=${SRS_CONTROL_SRATE_HZ}|g" /etc/srsran/ue.conf
      sed -i "s|max_nof_prb = 106|max_nof_prb = ${SRS_CONTROL_PRB}|g" /etc/srsran/ue.conf
      sed -i "s|nof_prb = 106|nof_prb = ${SRS_CONTROL_PRB}|g" /etc/srsran/ue.conf
      sed -i "s|ssb_nr_arfcn = 368410|ssb_nr_arfcn = ${SRS_CONTROL_SSB_ARFCN}|g" /etc/srsran/ue.conf
      sed -i "s|filename = /mnt/srslte/ue.log|filename = stdout|g" /etc/srsran/ue.conf
      sed -i "s|all_level = warning|all_level = info|g" /etc/srsran/ue.conf
      sed -i "s|phy_lib_level = none|phy_lib_level = warning|g" /etc/srsran/ue.conf
      exec /usr/local/bin/srsue /etc/srsran/ue.conf --ue.radio="${SRSUE_RADIO_MODE}" --ue.phy=nr --rat.nr.scs=15 --rat.nr.ssb_scs=15 --rf.time_adv_nsamples="${SRSUE_TIME_ADV_NSAMPLES}"
    ' >/dev/null
}

wait_for_log() {
  local container="$1"
  local pattern="$2"
  local seconds="${3:-90}"
  local logs

  for _ in $(seq 1 "$seconds"); do
    logs="$(docker logs --tail 4000 "$container" 2>&1 || true)"
    if grep -Eiq "$pattern" <<<"$logs"; then
      return 0
    fi
    if ! container_running "$container"; then
      echo "$container exited before '$pattern' appeared." >&2
      docker logs --tail 300 "$container" >&2 || true
      return 1
    fi
    sleep 1
  done

  echo "Timed out waiting for '$pattern' in $container logs." >&2
  docker logs --tail 300 "$container" >&2 || true
  return 1
}

wait_for_tun() {
  local container="$1"
  local seconds="${2:-120}"

  for _ in $(seq 1 "$seconds"); do
    if docker exec "$container" sh -lc 'ip -4 addr show tun_srsue 2>/dev/null | grep -q "inet "'; then
      return 0
    fi
    if ! container_running "$container"; then
      echo "$container exited before tun_srsue received an IPv4 address." >&2
      docker logs --tail 300 "$container" >&2 || true
      return 1
    fi
    sleep 1
  done

  echo "Timed out waiting for tun_srsue IPv4 address in $container." >&2
  docker logs --tail 300 "$container" >&2 || true
  return 1
}

check_smoke() {
  container_running "$GNB_CONTAINER"
  container_running "$UE_CONTAINER"
  if docker exec "$UE_CONTAINER" sh -lc 'ip -4 addr show tun_srsue 2>/dev/null | grep -q "inet "'; then
    echo "OK: control gNB + srsUE reached attach/session progress over ZMQ."
    return 0
  fi
  wait_for_log "$GNB_CONTAINER" 'NGSetupRequest|NGSetupResponse|Connected to AMF' 60
  wait_for_tun "$UE_CONTAINER" 120
  echo "OK: control gNB + srsUE reached attach/session progress over ZMQ."
}

start_smoke() {
  load_env
  "$SCRIPT_DIR/check_core_ready.sh" >/dev/null
  "$SCRIPT_DIR/provision_subscriber.sh" >/dev/null
  build_images
  stop_other_smoke_ues
  remove_containers
  run_gnb
  wait_for_log "$GNB_CONTAINER" 'Cell was activated|NG Setup procedure successful|NG Setup Request' 60
  run_ue
  echo "Started $GNB_CONTAINER and $UE_CONTAINER."
}

debug_smoke() {
  echo "== generated UE config =="
  docker exec "$UE_CONTAINER" sh -lc "sed -n '1,120p' /etc/srsran/ue.conf; sed -n '320,385p' /etc/srsran/ue.conf" 2>&1 || true
  echo
  echo "== srsUE process tree =="
  docker exec "$UE_CONTAINER" sh -lc 'ps -ef; ps -T -p 1 -o pid,tid,stat,pcpu,comm,wchan:40 2>/dev/null || true' 2>&1 || true
  echo
  echo "== srsUE thread wait channels =="
  docker exec "$UE_CONTAINER" sh -lc 'for t in /proc/1/task/*; do printf "%s " "${t##*/}"; cat "$t/comm" 2>/dev/null | tr "\n" " "; printf " "; cat "$t/wchan" 2>/dev/null || true; printf "\n"; done' 2>&1 || true
  echo
  echo "== srsUE ZMQ sockets =="
  docker exec "$UE_CONTAINER" sh -lc 'ss -tnpi 2>/dev/null || ss -tnp 2>/dev/null || true' 2>&1 || true
  echo
  echo "== recent logs =="
  show_logs
}

show_logs() {
  echo "== $GNB_CONTAINER =="
  docker logs --tail 180 "$GNB_CONTAINER" 2>&1 || true
  echo
  echo "== $UE_CONTAINER =="
  docker logs --tail 220 "$UE_CONTAINER" 2>&1 || true
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
    load_env
    build_images
    ;;
  check)
    check_smoke
    ;;
  logs)
    show_logs
    ;;
  down)
    remove_containers
    echo "Removed $GNB_CONTAINER and $UE_CONTAINER."
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
