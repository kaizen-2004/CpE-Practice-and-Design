#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

if [[ -f "$ROOT_DIR/deploy/systemd/thesis.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/deploy/systemd/thesis.env"
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
BROKER_HOST="${MQTT_BROKER_HOST:-127.0.0.1}"
BROKER_PORT="${MQTT_BROKER_PORT:-1883}"
TOPIC_ROOT="${MQTT_TOPIC_ROOT:-thesis/v1}"
API_URL="${SENSOR_EVENT_URL:-http://127.0.0.1:5000/api/sensors/event}"
MQTT_USER="${MQTT_BROKER_USERNAME:-}"
MQTT_PASS="${MQTT_BROKER_PASSWORD:-}"
SENSOR_API_KEY="${SENSOR_API_KEY:-}"
VISION_EVENT_SINK="${VISION_EVENT_SINK:-mqtt}"
CAMERA_MODE="${CAMERA_MODE:-esp32}"
OUTDOOR_URL="${OUTDOOR_URL:-}"
INDOOR_URL="${INDOOR_URL:-}"
ENABLE_VISION="${ENABLE_VISION:-1}"

usage() {
  cat <<'EOF'
Usage: pi/run_stack.sh [options]

Options:
  --no-vision                Run only Flask + MQTT ingest.
  --camera-mode MODE         Vision camera mode (default: esp32).
  --outdoor-url URL          Override OUTDOOR_URL for this run.
  --indoor-url URL           Override INDOOR_URL for this run.
  --python-bin PATH          Python executable to use.
  -h, --help                 Show this help.

Env (optional):
  MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_TOPIC_ROOT
  MQTT_BROKER_USERNAME, MQTT_BROKER_PASSWORD
  SENSOR_EVENT_URL, SENSOR_API_KEY
  OUTDOOR_URL, INDOOR_URL
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-vision)
      ENABLE_VISION="0"
      shift
      ;;
    --camera-mode)
      CAMERA_MODE="${2:-}"
      shift 2
      ;;
    --outdoor-url)
      OUTDOOR_URL="${2:-}"
      shift 2
      ;;
    --indoor-url)
      INDOOR_URL="${2:-}"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[stack] Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

PIDS=()

start_proc() {
  local name="$1"
  shift
  "$@" &
  local pid=$!
  PIDS+=("$pid")
  echo "[stack] started ${name} (pid=${pid})"
}

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

APP_CMD=("$PYTHON_BIN" "pi/app.py")
INGEST_CMD=(
  "$PYTHON_BIN" "pi/mqtt_ingest.py"
  "--broker-host" "$BROKER_HOST"
  "--broker-port" "$BROKER_PORT"
  "--topic-root" "$TOPIC_ROOT"
  "--api-url" "$API_URL"
)

if [[ -n "$MQTT_USER" ]]; then
  INGEST_CMD+=("--broker-username" "$MQTT_USER" "--broker-password" "$MQTT_PASS")
fi
if [[ -n "$SENSOR_API_KEY" ]]; then
  INGEST_CMD+=("--api-key" "$SENSOR_API_KEY")
fi

VISION_CMD=(
  "$PYTHON_BIN" "pi/vision_runtime.py"
  "--event-sink" "$VISION_EVENT_SINK"
  "--camera-mode" "$CAMERA_MODE"
  "--mqtt-host" "$BROKER_HOST"
  "--mqtt-port" "$BROKER_PORT"
  "--mqtt-topic-root" "$TOPIC_ROOT"
  "--api-url" "$API_URL"
)

if [[ -n "$MQTT_USER" ]]; then
  VISION_CMD+=("--mqtt-username" "$MQTT_USER" "--mqtt-password" "$MQTT_PASS")
fi
if [[ -n "$SENSOR_API_KEY" ]]; then
  VISION_CMD+=("--api-key" "$SENSOR_API_KEY")
fi
if [[ -n "$OUTDOOR_URL" ]]; then
  VISION_CMD+=("--outdoor-url" "$OUTDOOR_URL")
fi
if [[ -n "$INDOOR_URL" ]]; then
  VISION_CMD+=("--indoor-url" "$INDOOR_URL")
fi

echo "[stack] python=${PYTHON_BIN}"
echo "[stack] broker=${BROKER_HOST}:${BROKER_PORT} topic_root=${TOPIC_ROOT}"
echo "[stack] api=${API_URL}"
if [[ "$ENABLE_VISION" == "1" ]]; then
  echo "[stack] vision=enabled mode=${CAMERA_MODE}"
else
  echo "[stack] vision=disabled"
fi

start_proc "flask" "${APP_CMD[@]}"
start_proc "mqtt_ingest" "${INGEST_CMD[@]}"
if [[ "$ENABLE_VISION" == "1" ]]; then
  start_proc "vision_runtime" "${VISION_CMD[@]}"
fi

echo "[stack] all services running. Press Ctrl-C to stop."
wait -n
echo "[stack] one service exited; stopping remaining services."
exit 1
