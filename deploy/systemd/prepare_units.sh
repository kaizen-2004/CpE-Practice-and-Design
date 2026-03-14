#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_USER="$(id -un)"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"

SENSOR_EVENT_URL="http://127.0.0.1:5000/api/sensors/event"
SENSOR_API_KEY=""

MQTT_BROKER_HOST="127.0.0.1"
MQTT_BROKER_PORT="1883"
MQTT_BROKER_USERNAME="thesis_ingest"
MQTT_BROKER_PASSWORD="change_me"
MQTT_TOPIC_ROOT="thesis/v1"
MQTT_INGEST_CLIENT_ID="thesis-mqtt-ingest"
MQTT_INGEST_QOS="1"
MQTT_INGEST_RETRY_SECONDS="5"
MQTT_INGEST_STATUS_INTERVAL="20"

VISION_EVENT_SINK="mqtt"

OUT_DIR="$SCRIPT_DIR/generated"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="/usr/bin/python3"
fi

usage() {
  cat <<'EOF'
Usage: deploy/systemd/prepare_units.sh [options]

Options:
  --project-root PATH            Absolute project root path
  --run-user USER                User account for systemd services
  --python-bin PATH              Python binary used by services
  --sensor-event-url URL         API endpoint (default: http://127.0.0.1:5000/api/sensors/event)
  --sensor-api-key KEY           Optional X-API-KEY value
  --mqtt-broker-host HOST        MQTT broker host (default: 127.0.0.1)
  --mqtt-broker-port PORT        MQTT broker port (default: 1883)
  --mqtt-broker-username USER    MQTT username used by mqtt_ingest / vision
  --mqtt-broker-password PASS    MQTT password used by mqtt_ingest / vision
  --mqtt-topic-root ROOT         MQTT topic root (default: thesis/v1)
  --mqtt-ingest-client-id ID     MQTT ingest client id (default: thesis-mqtt-ingest)
  --mqtt-ingest-qos N            MQTT ingest QoS (default: 1)
  --mqtt-ingest-retry-seconds N  MQTT ingest retry seconds (default: 5)
  --mqtt-ingest-status-interval N MQTT ingest status interval (default: 20)
  --vision-event-sink MODE       vision_runtime sink: mqtt|api|db (default: mqtt)
  --out-dir DIR                  Output directory for rendered units
  -h, --help                     Show help

This script only generates files in the repo. It does not install systemd units.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="$2"
      shift 2
      ;;
    --run-user)
      RUN_USER="$2"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --sensor-event-url)
      SENSOR_EVENT_URL="$2"
      shift 2
      ;;
    --sensor-api-key)
      SENSOR_API_KEY="$2"
      shift 2
      ;;
    --mqtt-broker-host)
      MQTT_BROKER_HOST="$2"
      shift 2
      ;;
    --mqtt-broker-port)
      MQTT_BROKER_PORT="$2"
      shift 2
      ;;
    --mqtt-broker-username)
      MQTT_BROKER_USERNAME="$2"
      shift 2
      ;;
    --mqtt-broker-password)
      MQTT_BROKER_PASSWORD="$2"
      shift 2
      ;;
    --mqtt-topic-root)
      MQTT_TOPIC_ROOT="$2"
      shift 2
      ;;
    --mqtt-ingest-client-id)
      MQTT_INGEST_CLIENT_ID="$2"
      shift 2
      ;;
    --mqtt-ingest-qos)
      MQTT_INGEST_QOS="$2"
      shift 2
      ;;
    --mqtt-ingest-retry-seconds)
      MQTT_INGEST_RETRY_SECONDS="$2"
      shift 2
      ;;
    --mqtt-ingest-status-interval)
      MQTT_INGEST_STATUS_INTERVAL="$2"
      shift 2
      ;;
    --vision-event-sink)
      VISION_EVENT_SINK="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
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

if [[ ! "$PROJECT_ROOT" = /* ]]; then
  echo "Error: --project-root must be an absolute path." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

ENV_PATH="$SCRIPT_DIR/thesis.env"
cat > "$ENV_PATH" <<EOF
PROJECT_ROOT=$PROJECT_ROOT
PYTHON_BIN=$PYTHON_BIN
SENSOR_EVENT_URL=$SENSOR_EVENT_URL
SENSOR_API_KEY=$SENSOR_API_KEY
MQTT_BROKER_HOST=$MQTT_BROKER_HOST
MQTT_BROKER_PORT=$MQTT_BROKER_PORT
MQTT_BROKER_USERNAME=$MQTT_BROKER_USERNAME
MQTT_BROKER_PASSWORD=$MQTT_BROKER_PASSWORD
MQTT_TOPIC_ROOT=$MQTT_TOPIC_ROOT
MQTT_INGEST_CLIENT_ID=$MQTT_INGEST_CLIENT_ID
MQTT_INGEST_QOS=$MQTT_INGEST_QOS
MQTT_INGEST_RETRY_SECONDS=$MQTT_INGEST_RETRY_SECONDS
MQTT_INGEST_STATUS_INTERVAL=$MQTT_INGEST_STATUS_INTERVAL
VISION_EVENT_SINK=$VISION_EVENT_SINK
EOF

escape_sed() {
  printf '%s' "$1" | sed 's/[\/&]/\\&/g'
}

esc_project_root="$(escape_sed "$PROJECT_ROOT")"
esc_run_user="$(escape_sed "$RUN_USER")"

for tmpl in "$SCRIPT_DIR"/templates/*.tmpl; do
  name="$(basename "$tmpl" .tmpl)"
  out="$OUT_DIR/$name"
  sed \
    -e "s/__PROJECT_ROOT__/$esc_project_root/g" \
    -e "s/__RUN_USER__/$esc_run_user/g" \
    "$tmpl" > "$out"
done

echo "Generated:"
echo "  Env file:   $ENV_PATH"
echo "  Unit files: $OUT_DIR"
echo
echo "Next step on deployment machine:"
echo "  sudo bash deploy/systemd/install_units.sh --generated-dir $OUT_DIR --enable-stack --start-now"
