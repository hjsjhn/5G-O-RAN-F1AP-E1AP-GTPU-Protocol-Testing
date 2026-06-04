#!/usr/bin/env bash
# Run and validate registration + PDU Session or registration + inactivity-triggered Release.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FLOW="${1:-}"
RELEASE_TIMEOUT="${RELEASE_TIMEOUT:-240}"
COMPOSE_MAIN="$PROJECT_ROOT/docker/compose/docker-compose.yml"
COMPOSE_SPLIT="$PROJECT_ROOT/docker/compose/docker-compose.split.yml"
COMPOSE_EVIDENCE="$PROJECT_ROOT/docker/compose/docker-compose.flow-evidence.yml"

usage() {
  cat <<EOF
Usage: $0 [registration_pdu_session|registration_release]

The release flow keeps srsUE running and waits for the baseline CU-UP inactivity
timer to trigger E1AP/NGAP/F1AP release procedures. It does not treat stopping
the UE container as Deregistration.
EOF
}

if [[ "$FLOW" != "registration_pdu_session" && "$FLOW" != "registration_release" ]]; then
  usage >&2
  exit 2
fi

RUN_ID="${FLOW}_$(date +%Y%m%d_%H%M%S)"
CAPTURE_DIR="$PROJECT_ROOT/captures/raw/$RUN_ID"
RESULT_DIR="$PROJECT_ROOT/json/flow_results/$RUN_ID"
NORMALIZED_DIR="$RESULT_DIR/normalized"
TEMPLATE_DIR="$RESULT_DIR/templates"
LOG_DIR="$PROJECT_ROOT/logs/flows/$RUN_ID"
CAPTURE_ACTIVE=0
RESTORE_BASELINE=0

LOG_COMPONENTS="cu_cp cu_up du amf smf upf"
LOG_START_FILE="$RESULT_DIR/log_start.tsv"

log_container() {
  case "$1" in
    cu_cp) echo srsran_cu_cp ;;
    cu_up) echo srsran_cu_up ;;
    du) echo srsran_du ;;
    amf|smf|upf) echo "$1" ;;
  esac
}

log_path() {
  case "$1" in
    cu_cp) echo /tmp/cu_cp.log ;;
    cu_up) echo /tmp/cu_up.log ;;
    du) echo /tmp/du.log ;;
    amf|smf|upf) echo "/open5gs/install/var/log/open5gs/$1.log" ;;
  esac
}

log_lines() {
  local component="$1"
  case "$component" in
    cu_cp|cu_up)
      docker logs "$(log_container "$component")" 2>&1 | wc -l | tr -d ' '
      ;;
    *)
      docker exec "$(log_container "$component")" sh -lc "wc -l < '$(log_path "$component")' 2>/dev/null || echo 0"
      ;;
  esac
}

log_start() {
  local component="$1"
  awk -F '\t' -v component="$component" '$1 == component {print $2}' "$LOG_START_FILE"
}

snapshot_log_offsets() {
  local component
  : >"$LOG_START_FILE"
  for component in $LOG_COMPONENTS; do
    printf '%s\t%s\n' "$component" "$(log_lines "$component")" >>"$LOG_START_FILE"
  done
}

collect_logs() {
  mkdir -p "$LOG_DIR"
  local component start current
  for component in $LOG_COMPONENTS; do
    start="$(log_start "$component")"
    current="$(log_lines "$component")"
    if (( current < start )); then
      start=0
    fi
    case "$component" in
      cu_cp|cu_up)
        docker logs "$(log_container "$component")" 2>&1 | tail -n +$((start + 1)) >"$LOG_DIR/$component.log"
        ;;
      *)
        docker exec "$(log_container "$component")" sh -lc \
          "tail -n +$((start + 1)) '$(log_path "$component")' 2>/dev/null || true" \
          >"$LOG_DIR/$component.log"
        ;;
    esac
  done
  docker logs srsue_5g_zmq >"$LOG_DIR/ue.log" 2>&1 || true
}

stop_capture_if_active() {
  if (( CAPTURE_ACTIVE == 1 )); then
    "$PROJECT_ROOT/scripts/capture/capture_traffic.sh" stop >/dev/null 2>&1 || true
    CAPTURE_ACTIVE=0
  fi
}

cleanup() {
  stop_capture_if_active
  if (( RESTORE_BASELINE == 1 )); then
    "$PROJECT_ROOT/scripts/env/run_srsue_zmq_smoke.sh" down >/dev/null 2>&1 || true
    docker compose -f "$COMPOSE_MAIN" -f "$COMPOSE_SPLIT" \
      up -d --force-recreate cu-cp cu-up du >/dev/null 2>&1 || true
    for _ in $(seq 1 60); do
      if "$PROJECT_ROOT/scripts/env/check_core_ready.sh" >/dev/null 2>&1; then
        break
      fi
      sleep 2
    done
    RESTORE_BASELINE=0
  fi
}
trap cleanup EXIT

prepare_flow_evidence_environment() {
  docker compose -f "$COMPOSE_MAIN" -f "$COMPOSE_SPLIT" -f "$COMPOSE_EVIDENCE" \
    up -d --force-recreate cu-cp cu-up du >/dev/null
  RESTORE_BASELINE=1

  for _ in $(seq 1 90); do
    if "$PROJECT_ROOT/scripts/env/check_core_ready.sh" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  "$PROJECT_ROOT/scripts/env/check_core_ready.sh"
}

wait_for_release() {
  local ue_logs
  for _ in $(seq 1 "$RELEASE_TIMEOUT"); do
    ue_logs="$(docker logs --tail 12000 srsue_5g_zmq 2>&1 || true)"
    if grep -q "Received RRC Release" <<<"$ue_logs"; then
      return 0
    fi
    if [[ "$(docker inspect -f '{{.State.Running}}' srsue_5g_zmq 2>/dev/null || true)" != "true" ]]; then
      echo "srsUE stopped before the inactivity-triggered release completed." >&2
      return 1
    fi
    sleep 1
  done
  echo "Timed out waiting for inactivity-triggered release after ${RELEASE_TIMEOUT}s." >&2
  return 1
}

cd "$PROJECT_ROOT"
mkdir -p "$CAPTURE_DIR" "$RESULT_DIR" "$NORMALIZED_DIR" "$TEMPLATE_DIR" "$LOG_DIR"
./scripts/env/check_core_ready.sh
prepare_flow_evidence_environment
snapshot_log_offsets
./scripts/capture/capture_traffic.sh start "$CAPTURE_DIR"
CAPTURE_ACTIVE=1
SRSUE_RECREATE_DU=0 ./scripts/env/run_srsue_zmq_smoke.sh run

docker exec srsue_5g_zmq sh -lc '
  ip route replace 8.8.8.8 dev tun_srsue
  ping -I tun_srsue -c 1 -W 1 8.8.8.8 >/tmp/ue_flow_ping.log 2>&1 || true
' || true

if [[ "$FLOW" == "registration_release" ]]; then
  echo "Waiting for legitimate inactivity-triggered release while srsUE remains running..."
  wait_for_release
fi

sleep 2
stop_capture_if_active
collect_logs

python3 scripts/parse/normalize_pcaps.py \
  --sctp-pcap "$CAPTURE_DIR/ran_sctp_full.pcap" \
  --gtpu-pcap "$CAPTURE_DIR/gtpu_full.pcap" \
  --prefix "$RUN_ID" \
  -o "$NORMALIZED_DIR"

CONTROL="$NORMALIZED_DIR/${RUN_ID}_control_plane_packets.json"
GTPU="$NORMALIZED_DIR/${RUN_ID}_gtpu_packets.json"
python3 scripts/flows/extract_templates.py \
  --run-id "$RUN_ID" \
  --sctp-pcap "$CAPTURE_DIR/ran_sctp_full.pcap" \
  --gtpu-pcap "$CAPTURE_DIR/gtpu_full.pcap" \
  --control "$CONTROL" \
  --gtpu "$GTPU" \
  --output-dir "$TEMPLATE_DIR"

python3 scripts/flows/analyze_flow.py \
  --flow "$FLOW" \
  --run-id "$RUN_ID" \
  --control "$CONTROL" \
  --gtpu "$GTPU" \
  --log-dir "$LOG_DIR" \
  --output "$RESULT_DIR/result.json"
