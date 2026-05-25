#!/usr/bin/env bash
# Run the phase-4 pcap -> tshark JSON -> normalized JSON pipeline.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RUN_DIR="${1:-}"
if [[ -z "$RUN_DIR" ]]; then
  RUN_DIR="$(find "$PROJECT_ROOT/captures/raw" -maxdepth 1 -type d -name 'run_capture_ping_*' | sort | tail -1)"
fi

if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  echo "No capture run directory found. Pass one explicitly." >&2
  exit 1
fi

SCTP_PCAP="$RUN_DIR/ran_sctp_full.pcap"
GTPU_PCAP="$RUN_DIR/gtpu_full.pcap"

if [[ ! -f "$SCTP_PCAP" ]]; then
  echo "Missing SCTP pcap: $SCTP_PCAP" >&2
  exit 1
fi
if [[ ! -f "$GTPU_PCAP" ]]; then
  echo "Missing GTP-U pcap: $GTPU_PCAP" >&2
  exit 1
fi

RUN_NAME="$(basename "$RUN_DIR")"

cd "$PROJECT_ROOT"
python3 scripts/parse/pcap_to_tshark_json.py "$SCTP_PCAP" "$GTPU_PCAP" --prefix "$RUN_NAME" -o json/tshark_raw
python3 scripts/parse/normalize_pcaps.py \
  --sctp-pcap "$SCTP_PCAP" \
  --gtpu-pcap "$GTPU_PCAP" \
  --prefix "$RUN_NAME" \
  -o json/normalized
