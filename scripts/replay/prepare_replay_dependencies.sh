#!/usr/bin/env bash
# Prepare or verify the pinned srsRAN source and ASN.1 builder image used by replay tools.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/docker/srsran-src"
SRSRAN_REPOSITORY="https://github.com/srsran/srsRAN_Project.git"
EXPECTED_SRSRAN_COMMIT="4bf1543936d062686d64c10724d2f27a9854f065"
BUILDER_IMAGE="pavonis/srs-gnb-dev@sha256:820ba5ed9056ba8f913ef6b749bf24cd72127ceadf040d60fbc56193368bb344"
MODE="${1:---check}"

usage() {
  echo "Usage: $0 [--check|--prepare]" >&2
}

check_dependencies() {
  if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    echo "ERROR: missing pinned srsRAN source at $SOURCE_DIR" >&2
    return 1
  fi
  local actual_commit
  actual_commit="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
  if [[ "$actual_commit" != "$EXPECTED_SRSRAN_COMMIT" ]]; then
    echo "ERROR: srsRAN source commit mismatch: expected $EXPECTED_SRSRAN_COMMIT, got $actual_commit" >&2
    return 1
  fi
  if ! docker image inspect "$BUILDER_IMAGE" >/dev/null 2>&1; then
    echo "ERROR: missing pinned builder image: $BUILDER_IMAGE" >&2
    return 1
  fi
  echo "OK: replay dependencies are pinned and available."
}

case "$MODE" in
  --check)
    check_dependencies
    ;;
  --prepare)
    if [[ ! -d "$SOURCE_DIR/.git" ]]; then
      if [[ -e "$SOURCE_DIR" ]]; then
        echo "ERROR: refusing to replace non-git path at $SOURCE_DIR" >&2
        exit 2
      fi
      git clone --no-checkout "$SRSRAN_REPOSITORY" "$SOURCE_DIR"
    fi
    if [[ -n "$(git -C "$SOURCE_DIR" status --porcelain)" ]]; then
      echo "ERROR: refusing to change dirty srsRAN source checkout at $SOURCE_DIR" >&2
      exit 2
    fi
    if ! git -C "$SOURCE_DIR" cat-file -e "${EXPECTED_SRSRAN_COMMIT}^{commit}" 2>/dev/null; then
      git -C "$SOURCE_DIR" fetch origin "$EXPECTED_SRSRAN_COMMIT"
    fi
    git -C "$SOURCE_DIR" checkout --detach "$EXPECTED_SRSRAN_COMMIT"
    docker pull "$BUILDER_IMAGE"
    check_dependencies
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
