#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$ROOT_DIR/.arduino-build/mqtt"

if ! command -v arduino-cli >/dev/null 2>&1; then
  echo "arduino-cli is required but not found." >&2
  exit 1
fi

if ! arduino-cli lib list | grep -Eq '^PubSubClient[[:space:]]'; then
  echo "Missing Arduino library: PubSubClient" >&2
  echo "Install when internet is available:" >&2
  echo "  arduino-cli lib install PubSubClient" >&2
  exit 1
fi

mkdir -p "$BUILD_DIR"

compile_sketch() {
  local fqbn="$1"
  local sketch_rel="$2"
  local name
  name="$(basename "$sketch_rel")"

  echo "==> Compiling $sketch_rel ($fqbn)"
  arduino-cli compile \
    --fqbn "$fqbn" \
    --build-path "$BUILD_DIR/$name" \
    "$ROOT_DIR/$sketch_rel"
}

compile_sketch "esp32:esp32:esp32c3" "firmware/mqtt/smoke_node1_mqtt"
compile_sketch "esp32:esp32:esp32c3" "firmware/mqtt/smoke_node2_mqtt"
compile_sketch "esp32:esp32:esp32c3" "firmware/mqtt/door_force_mqtt"
compile_sketch "esp32:esp32:esp32cam" "firmware/mqtt/cam_outdoor_mqtt"
compile_sketch "esp32:esp32:esp32cam" "firmware/mqtt/cam_indoor_mqtt"

echo
echo "All MQTT firmware sketches compiled successfully."
