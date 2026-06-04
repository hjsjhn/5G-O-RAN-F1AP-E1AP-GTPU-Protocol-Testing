#!/usr/bin/env bash
# Run available Stage 5C.4 live tests. Defaults to a non-sending dry run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MODE="${1:-}"
OUTPUT_DIR="$PROJECT_ROOT/json/replay_results/stage5c4"
RESTORE_ON_EXIT=0

on_exit() {
  local test_status="$1"
  local restore_status=0
  trap - EXIT
  set +e
  if (( RESTORE_ON_EXIT == 1 )); then
    "$PROJECT_ROOT/scripts/env/restore_baseline.sh"
    restore_status=$?
  fi
  if (( test_status != 0 )); then
    echo "Live runner failed with status ${test_status}; baseline restore status=${restore_status}." >&2
    exit "$test_status"
  fi
  if (( restore_status != 0 )); then
    echo "ERROR: live runner completed but baseline restoration failed." >&2
    exit "$restore_status"
  fi
  exit 0
}
trap 'on_exit $?' EXIT

usage() {
  cat <<EOF
Usage: $0 [--dry-run|--live]

--dry-run  Check the baseline and print the isolated live scenario without sending.
--live     Run JSON-generated same-payload F1AP/E1AP peer tests, GTP-U replay, and NGAP mutation entry.
EOF
}

cd "$PROJECT_ROOT"
mkdir -p "$OUTPUT_DIR"

case "$MODE" in
  ""|--dry-run)
    ./scripts/env/check_core_ready.sh
    python3 scripts/replay/run_control_peer_validation.py \
      --output "$OUTPUT_DIR/control_peer_dry_run.json"
    python3 scripts/replay/run_ngap_open5gs_test.py --output "$OUTPUT_DIR/ngap_dry_run.json"
    cat <<EOF
DRY-RUN: no live packets or new SCTP associations were created.
Live mode generates F1AP/E1AP payloads from JSON, validates them with tshark,
passes the same bytes to an isolated protocol-aware SCTP endpoint, creates a
normal UE session only as GTP-U precondition, injects the generated GTP-U
testcase, and runs a separately labelled NGAP config mutation.
EOF
    ;;
  --live)
    RESTORE_ON_EXIT=1
    ./scripts/env/check_core_ready.sh
    if [[ "${LIVE_RUNNER_TEST_EXIT_AFTER_PREP:-0}" == "1" ]]; then
      echo "TEST-ONLY: exiting successfully before live tests to exercise restoration." >&2
      exit 0
    fi
    python3 scripts/replay/run_control_peer_validation.py \
      --live \
      --output "$OUTPUT_DIR/control_peer_validation.json"
    FLOW_LIVE_GTPU_REPLAY=1 ./scripts/flows/run_ue_flow.sh registration_pdu_session
    python3 scripts/replay/run_ngap_open5gs_test.py \
      --live \
      --case tests/replay/ngap_cases/tac_mismatch.json \
      --output "$OUTPUT_DIR/ngap_open5gs.json"
    ./scripts/env/check_core_ready.sh
    echo "PASS: JSON-generated same-payload F1AP/E1AP peer tests, GTP-U live replay, and NGAP mutation entry"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
