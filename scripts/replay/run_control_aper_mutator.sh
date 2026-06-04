#!/usr/bin/env bash
# Build and run the pinned srsRAN ASN.1 control-message mutator.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/docker/srsran-src"
BUILD_DIR="${CONTROL_APER_BUILD_DIR:-${TMPDIR:-/tmp}/srsran-control-aper-build}"
EXPECTED_SRSRAN_COMMIT="4bf1543936d062686d64c10724d2f27a9854f065"
BUILDER_IMAGE="${CONTROL_APER_BUILDER_IMAGE:-pavonis/srs-gnb-dev@sha256:820ba5ed9056ba8f913ef6b749bf24cd72127ceadf040d60fbc56193368bb344}"
BUILDER_PLATFORM="${CONTROL_APER_BUILDER_PLATFORM:-linux/amd64}"

if [[ "$#" -ne 5 ]]; then
  echo "Usage: $0 PROTOCOL MESSAGE PAYLOAD_HEX FIELD VALUE" >&2
  exit 2
fi
if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  echo "Missing pinned local srsRAN source at $SOURCE_DIR" >&2
  exit 3
fi
actual_commit="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
if [[ "$actual_commit" != "$EXPECTED_SRSRAN_COMMIT" ]]; then
  echo "srsRAN source commit mismatch: expected $EXPECTED_SRSRAN_COMMIT, got $actual_commit" >&2
  exit 4
fi

mkdir -p "$BUILD_DIR"
if [[ ! -x "$BUILD_DIR/control_aper_mutator" || "$SCRIPT_DIR/control_aper_mutator.cpp" -nt "$BUILD_DIR/control_aper_mutator" ]]; then
  docker run --rm --platform "$BUILDER_PLATFORM" \
    -v "$SOURCE_DIR:/src:ro" -v "$BUILD_DIR:/build" \
    -v "$SCRIPT_DIR/control_aper_mutator.cpp:/tmp/control_aper_mutator.cpp:ro" \
    --entrypoint /bin/sh "$BUILDER_IMAGE" -c \
    'cmake -S /src -B /build -DBUILD_TESTING=OFF -DENABLE_UHD=OFF -DENABLE_ZEROMQ=OFF &&
     cmake --build /build --target f1ap_asn1 e1ap_asn1 -j2 &&
     g++ -std=gnu++17 -O2 -DASSERTS_ENABLED -I/src/include -I/src/external/fmt/include -I/src/external \
       /tmp/control_aper_mutator.cpp \
       /build/lib/asn1/libf1ap_asn1.a /build/lib/asn1/libe1ap_asn1.a /build/lib/asn1/libasn1_utils.a \
       /build/lib/srslog/libsrslog.a /build/lib/support/libsrsran_support.a /build/external/fmt/libfmt.a \
       -lyaml-cpp -lpthread -ldl -lrt -latomic -o /build/control_aper_mutator'
fi

docker run --rm --platform "$BUILDER_PLATFORM" \
  -v "$BUILD_DIR:/build:ro" \
  --entrypoint /build/control_aper_mutator "$BUILDER_IMAGE" "$@"
