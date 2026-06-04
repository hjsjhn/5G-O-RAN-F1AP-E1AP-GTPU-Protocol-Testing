#!/usr/bin/env bash
# Encode replay testcases and validate generated pcaps with tshark.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"
python3 scripts/replay/run_replay_tests.py "$@"
