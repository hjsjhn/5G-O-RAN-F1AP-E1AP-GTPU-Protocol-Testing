#!/usr/bin/env bash
# Capture full network-frame SCTP and GTP-U pcaps from the target RAN containers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATE_FILE="$PROJECT_ROOT/captures/raw/.active_capture_dir"
DEFAULT_DIR="$PROJECT_ROOT/captures/raw/run_$(date +%Y%m%d_%H%M%S)"
CAPTURE_DIR="${2:-$DEFAULT_DIR}"

CU_CP_CONTAINER="${CU_CP_CONTAINER:-srsran_cu_cp}"
CU_UP_CONTAINER="${CU_UP_CONTAINER:-srsran_cu_up}"
UE_CONTAINER="${UE_CONTAINER:-srsue_5g_zmq}"
SCTP_PCAP="/tmp/ran_sctp_full.pcap"
GTPU_PCAP="/tmp/gtpu_full.pcap"

usage() {
  cat <<EOF
Usage: $0 [run|start|stop|status] [capture_dir]

Commands:
  run [dir]    Start capture, run srsUE smoke, generate UE ping traffic, stop and copy pcaps.
  start [dir]  Start tcpdump inside CU-CP and CU-UP containers.
  stop         Stop tcpdump and copy pcaps to the active capture dir.
  status       Show tcpdump processes and current pcap sizes.

Notes:
  - Uses in-container tcpdump, not sidecar capture containers.
  - CU-CP captures SCTP: NGAP, E1AP, F1AP.
  - CU-UP captures UDP/2152: F1-U and N3 GTP-U.
EOF
}

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" == "true" ]]
}

require_container() {
  local container="$1"
  if ! container_running "$container"; then
    echo "Container $container is not running." >&2
    exit 1
  fi
}

ensure_tcpdump() {
  local container="$1"
  if docker exec "$container" sh -lc 'command -v tcpdump >/dev/null 2>&1'; then
    return 0
  fi

  echo "Installing tcpdump in $container..."
  docker exec "$container" sh -lc 'apt-get update -qq && apt-get install -y -qq tcpdump >/dev/null'
}

stop_tcpdump_in_container() {
  local container="$1"
  docker exec "$container" sh -lc 'pkill -TERM tcpdump 2>/dev/null || true' >/dev/null 2>&1 || true
}

start_tcpdump() {
  local container="$1"
  local pcap_path="$2"
  local filter="$3"

  ensure_tcpdump "$container"
  stop_tcpdump_in_container "$container"
  docker exec "$container" sh -lc "rm -f '$pcap_path'; tcpdump -i any -s 0 -U -w '$pcap_path' '$filter' >/tmp/oran_tcpdump.log 2>&1 &"
}

start_capture() {
  require_container "$CU_CP_CONTAINER"
  require_container "$CU_UP_CONTAINER"
  mkdir -p "$CAPTURE_DIR"
  printf '%s\n' "$CAPTURE_DIR" > "$STATE_FILE"

  echo "Starting in-container capture..."
  start_tcpdump "$CU_CP_CONTAINER" "$SCTP_PCAP" "sctp"
  start_tcpdump "$CU_UP_CONTAINER" "$GTPU_PCAP" "udp port 2152"

  echo "Capturing to: $CAPTURE_DIR"
  echo "  $CU_CP_CONTAINER:$SCTP_PCAP -> ran_sctp_full.pcap"
  echo "  $CU_UP_CONTAINER:$GTPU_PCAP -> gtpu_full.pcap"
}

copy_pcap() {
  local container="$1"
  local src="$2"
  local dst="$3"
  if docker exec "$container" sh -lc "[ -f '$src' ]"; then
    docker cp "$container:$src" "$dst"
  else
    echo "Missing $container:$src" >&2
  fi
}

stop_capture() {
  local dir
  if [[ -f "$STATE_FILE" ]]; then
    dir="$(cat "$STATE_FILE")"
  else
    dir="$CAPTURE_DIR"
  fi
  mkdir -p "$dir"

  echo "Stopping tcpdump..."
  stop_tcpdump_in_container "$CU_CP_CONTAINER"
  stop_tcpdump_in_container "$CU_UP_CONTAINER"
  sleep 1

  copy_pcap "$CU_CP_CONTAINER" "$SCTP_PCAP" "$dir/ran_sctp_full.pcap"
  copy_pcap "$CU_UP_CONTAINER" "$GTPU_PCAP" "$dir/gtpu_full.pcap"
  rm -f "$STATE_FILE"

  echo "Capture saved to: $dir"
  ls -lh "$dir"/*.pcap 2>/dev/null || true
}

show_status() {
  for container in "$CU_CP_CONTAINER" "$CU_UP_CONTAINER"; do
    echo "== $container =="
    if ! container_running "$container"; then
      echo "not running"
      continue
    fi
    docker exec "$container" sh -lc 'pgrep -a tcpdump || true; ls -lh /tmp/*full.pcap 2>/dev/null || true'
  done
}

generate_ue_traffic() {
  if ! container_running "$UE_CONTAINER"; then
    echo "UE container $UE_CONTAINER is not running; skipping UE ping traffic." >&2
    return 0
  fi
  docker exec "$UE_CONTAINER" sh -lc '
    set -e
    ip -4 addr show tun_srsue >/dev/null 2>&1
    if ! command -v ping >/dev/null 2>&1; then
      apt-get update -qq
      apt-get install -y -qq iputils-ping >/dev/null
    fi
    ip route replace 8.8.8.8 dev tun_srsue
    ping -I tun_srsue -c 5 -W 1 8.8.8.8 >/tmp/ue_ping_8.8.8.8.log 2>&1 || true
  '
}

run_capture() {
  start_capture
  "$PROJECT_ROOT/scripts/env/run_srsue_zmq_smoke.sh" run
  generate_ue_traffic
  stop_capture
}

cmd="${1:-usage}"
case "$cmd" in
  run)
    run_capture
    ;;
  start)
    start_capture
    ;;
  stop)
    stop_capture
    ;;
  status)
    show_status
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
