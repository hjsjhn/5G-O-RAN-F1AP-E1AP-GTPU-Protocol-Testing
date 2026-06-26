#!/usr/bin/env bash
# Rebuild XnAP templates with srsRAN generated ASN.1 code and compare committed payloads.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/docker/srsran-src"
BUILD_DIR="${XNAP_BUILD_DIR:-${TMPDIR:-/tmp}/srsran-xnap-template-build}"
EXPECTED_SRSRAN_COMMIT="4bf1543936d062686d64c10724d2f27a9854f065"
BUILDER_IMAGE="${XNAP_BUILDER_IMAGE:-pavonis/srs-gnb-dev@sha256:820ba5ed9056ba8f913ef6b749bf24cd72127ceadf040d60fbc56193368bb344}"
BUILDER_PLATFORM="${XNAP_BUILDER_PLATFORM:-linux/amd64}"

if [[ ! -d "$SOURCE_DIR/.git" || ! -f "$SOURCE_DIR/include/srsran/asn1/xnap/xnap.h" ]]; then
  echo "Missing local srsRAN source at $SOURCE_DIR" >&2
  exit 2
fi
actual_commit="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
if [[ "$actual_commit" != "$EXPECTED_SRSRAN_COMMIT" ]]; then
  echo "srsRAN source commit mismatch: expected $EXPECTED_SRSRAN_COMMIT, got $actual_commit" >&2
  exit 3
fi

mkdir -p "$BUILD_DIR"

docker run --rm --platform "$BUILDER_PLATFORM" \
  -v "$SOURCE_DIR:/src:ro" -v "$BUILD_DIR:/build" \
  --entrypoint /bin/sh "$BUILDER_IMAGE" -c \
  'cmake -S /src -B /build -DBUILD_TESTING=OFF -DENABLE_UHD=OFF -DENABLE_ZEROMQ=OFF &&
   cmake --build /build --target xnap_asn1 ngap_asn1 -j2'

OUTPUT="$(
  docker run --rm --platform "$BUILDER_PLATFORM" \
    -v "$SOURCE_DIR:/src:ro" -v "$BUILD_DIR:/build" \
    -v "$SCRIPT_DIR/xnap_template_generator.cpp:/tmp/xnap_template_generator.cpp:ro" \
    --entrypoint /bin/sh "$BUILDER_IMAGE" -c \
    'g++ -std=gnu++17 -O2 -DASSERTS_ENABLED -I/src/include -I/src/external/fmt/include -I/src/external \
       /tmp/xnap_template_generator.cpp \
       /build/lib/asn1/libxnap_asn1.a /build/lib/asn1/libngap_asn1.a /build/lib/asn1/libasn1_utils.a \
       /build/lib/srslog/libsrslog.a /build/lib/support/libsrsran_support.a /build/external/fmt/libfmt.a \
       -lyaml-cpp -lsctp -lpthread -ldl -lrt -latomic -o /build/xnap_template_generator &&
     /build/xnap_template_generator'
)"

XNAP_GENERATOR_OUTPUT="$OUTPUT" python3 - "$PROJECT_ROOT" <<'PY'
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
actual = dict(line.split(" ", 1) for line in os.environ["XNAP_GENERATOR_OUTPUT"].splitlines())
templates = {
    "HandoverRequest": root / "tests/replay/templates/stage5c3/xnap/handover_request.json",
    "HandoverRequestAcknowledge": root
    / "tests/replay/templates/stage5c3/xnap/handover_request_acknowledge.json",
}
for name, path in templates.items():
    expected = json.loads(path.read_text(encoding="utf-8"))["payload"]["hex"]
    if actual.get(name) != expected:
        raise SystemExit(f"{name}: generated payload differs from {path}")
    print(f"[PASS] {name} generated payload matches committed template")
PY
