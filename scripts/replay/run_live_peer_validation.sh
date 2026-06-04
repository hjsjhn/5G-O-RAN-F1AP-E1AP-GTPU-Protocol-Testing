#!/usr/bin/env bash
# Run Stage 5C.4 peer validation. Defaults to a non-sending dry run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MODE="${1:-}"
OUTPUT_DIR="$PROJECT_ROOT/json/replay_results/stage5c4"

usage() {
  cat <<EOF
Usage: $0 [--dry-run|--live]

--dry-run  Check the baseline and print the isolated live scenario without sending.
--live     Run controlled F1AP/E1AP flows, dynamic GTP-U replay, and NGAP/Open5GS test.
EOF
}

latest_flow_dir() {
  local prefix="$1"
  find "$PROJECT_ROOT/json/flow_results" -maxdepth 1 -type d -name "${prefix}_*" -print \
    | sort | tail -1
}

cd "$PROJECT_ROOT"
mkdir -p "$OUTPUT_DIR"

case "$MODE" in
  ""|--dry-run)
    ./scripts/env/check_core_ready.sh
    python3 scripts/replay/run_ngap_open5gs_test.py --output "$OUTPUT_DIR/ngap_dry_run.json"
    cat <<EOF
DRY-RUN: no live packets or new SCTP associations were created.
Live mode runs the two controlled UE flows, injects GTP-U only from the local
UPF namespace to the current CU-UP endpoint/TEID, and uses UERANSIM as the
protocol-aware NGAP/Open5GS test endpoint.
EOF
    ;;
  --live)
    ./scripts/env/check_core_ready.sh
    FLOW_LIVE_GTPU_REPLAY=1 ./scripts/flows/run_ue_flow.sh registration_pdu_session
    PDU_RESULT_DIR="$(latest_flow_dir registration_pdu_session)"
    ./scripts/env/check_core_ready.sh
    ./scripts/flows/run_ue_flow.sh registration_release
    RELEASE_RESULT_DIR="$(latest_flow_dir registration_release)"
    ./scripts/env/check_core_ready.sh
    python3 scripts/replay/validate_peer_scenario.py \
      --pdu-result-dir "$PDU_RESULT_DIR" \
      --release-result-dir "$RELEASE_RESULT_DIR" \
      --output "$OUTPUT_DIR/peer_validation.json"
    python3 scripts/replay/run_ngap_open5gs_test.py \
      --live \
      --output "$OUTPUT_DIR/ngap_open5gs.json"
    ./scripts/env/check_core_ready.sh
    echo "PASS: Stage 5C.4 live peer validation"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
