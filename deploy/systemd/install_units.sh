#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GENERATED_DIR="$SCRIPT_DIR/generated"
SYSTEMD_DIR="/etc/systemd/system"
ENABLE_STACK="0"
ENABLE_VISION="0"
START_NOW="0"

usage() {
  cat <<'EOF'
Usage: sudo deploy/systemd/install_units.sh [options]

Options:
  --generated-dir DIR   Directory containing rendered unit files
  --systemd-dir DIR     Systemd unit destination (default: /etc/systemd/system)
  --enable-stack        Enable thesis-stack.target
  --enable-vision       Enable thesis-vision.service
  --start-now           Restart app + mqtt-ingest (+vision if enabled) and start target now
  -h, --help            Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --generated-dir)
      GENERATED_DIR="$2"
      shift 2
      ;;
    --systemd-dir)
      SYSTEMD_DIR="$2"
      shift 2
      ;;
    --enable-stack)
      ENABLE_STACK="1"
      shift
      ;;
    --enable-vision)
      ENABLE_VISION="1"
      shift
      ;;
    --start-now)
      START_NOW="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run this script with sudo/root." >&2
  exit 1
fi

required_units=(
  "thesis-app.service"
  "thesis-mqtt-ingest.service"
  "thesis-stack.target"
)

for unit in "${required_units[@]}"; do
  if [[ ! -f "$GENERATED_DIR/$unit" ]]; then
    echo "Missing unit file: $GENERATED_DIR/$unit" >&2
    echo "Run deploy/systemd/prepare_units.sh first." >&2
    exit 1
  fi
done

install -m 0644 "$GENERATED_DIR/thesis-app.service" "$SYSTEMD_DIR/thesis-app.service"
install -m 0644 "$GENERATED_DIR/thesis-mqtt-ingest.service" "$SYSTEMD_DIR/thesis-mqtt-ingest.service"
install -m 0644 "$GENERATED_DIR/thesis-stack.target" "$SYSTEMD_DIR/thesis-stack.target"

if [[ -f "$GENERATED_DIR/thesis-vision.service" ]]; then
  install -m 0644 "$GENERATED_DIR/thesis-vision.service" "$SYSTEMD_DIR/thesis-vision.service"
fi

systemctl daemon-reload

if [[ "$ENABLE_STACK" == "1" ]]; then
  systemctl enable thesis-stack.target
fi

if [[ "$ENABLE_VISION" == "1" ]]; then
  systemctl enable thesis-vision.service
fi

if [[ "$START_NOW" == "1" ]]; then
  systemctl restart thesis-app.service
  systemctl restart thesis-mqtt-ingest.service
  if [[ "$ENABLE_VISION" == "1" ]]; then
    systemctl restart thesis-vision.service
  fi
  systemctl start thesis-stack.target
fi

echo "Installed unit files to $SYSTEMD_DIR."
echo "Check status with:"
echo "  systemctl status thesis-app.service thesis-mqtt-ingest.service thesis-stack.target"
echo "Optional vision:"
echo "  systemctl status thesis-vision.service"
