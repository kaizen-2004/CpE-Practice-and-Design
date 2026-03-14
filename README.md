# Condo Monitoring System (MQTT Local-First)

Local-first condo monitoring system for:
- Intruder detection (face recognition)
- Fire detection (smoke + flame fusion)
- Alerts, snapshots, history, and Telegram notifications

Scope: **Living Room** and **Door Entrance Area** only.

## Architecture (Active)

```text
ESP32 nodes/cameras -> MQTT (Wi-Fi) -> Mosquitto (Pi) -> pi/mqtt_ingest.py
-> POST /api/sensors/event -> Flask + SQLite + fusion + React dashboard + Telegram
```

Video transport is HTTP MJPEG from ESP32-CAM (`:81/stream`).  
MQTT carries camera status/control/events, not video frames.

## Core Runtime

- Flask backend/UI: `pi/app.py`
- MQTT ingest bridge: `pi/mqtt_ingest.py`
- Vision runtime: `pi/vision_runtime.py`
- Fusion logic: `pi/fusion.py`
- Notifications: `pi/notifications.py`

## Setup

```bash
python -m venv .venv
# activate venv
pip install -r requirements.txt
python pi/init_db.py
```

Install broker on Pi:

```bash
sudo apt install -y mosquitto mosquitto-clients
```

## Run (Manual)

Terminal 1:

```bash
python pi/app.py
```

Terminal 2:

```bash
python pi/mqtt_ingest.py
```

Terminal 3 (vision, Pi or laptop fallback):

```bash
python pi/vision_runtime.py --event-sink mqtt --camera-mode esp32 \
  --outdoor-url http://OUTDOOR_IP:81/stream \
  --indoor-url http://INDOOR_IP:81/stream
```

Open: `http://127.0.0.1:5000/dashboard`

## Integrated Dashboard (Flask + React)

The dashboard frontend lives in `web_dashboard_ui/` and is served by Flask at `/dashboard`.

Build it when UI code changes:

```bash
cd web_dashboard_ui
npm install
npm run build
```

Then run Flask normally:

```bash
cd ..
python pi/app.py
```

Notes:
- React SPA route: `/dashboard` (and `/dashboard/...`).
- Legacy Jinja dashboard remains available at `/dashboard-legacy`.
- Set `REACT_DASHBOARD_ENABLED=0` to force legacy dashboard mode.

## Sensor/Event Contract (Preserved)

Backend endpoint remains:

- `POST /api/sensors/event`

Event names preserved:

- Intruder-related: `UNKNOWN`, `AUTHORIZED`, `DOOR_FORCE`
- Fire-related: `FLAME_SIGNAL`, `SMOKE_HIGH`, `SMOKE_NORMAL`

Fusion behavior preserved:

- `FIRE` requires recent `SMOKE_HIGH` + recent indoor `FLAME_SIGNAL`
- `INTRUDER` requires 2-of-3 evidence:
  - outdoor unknown
  - indoor unknown
  - door force
- door-force alone still falls back to `DOOR_FORCE` alert

## MQTT Topics

Root: `thesis/v1`

- `thesis/v1/events/<node>`
- `thesis/v1/status/<node>`
- `thesis/v1/camera/<node>/control`
- `thesis/v1/camera/<node>/ack`

Supported node IDs:

- `mq2_living`
- `mq2_door`
- `door_force`
- `cam_indoor`
- `cam_outdoor`

## Environment Variables

Application:
- `SENSOR_EVENT_URL` (default `http://127.0.0.1:5000/api/sensors/event`)
- `SENSOR_API_KEY` (optional; enforced by Flask when set)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `PUBLIC_BASE_URL`
- `TELEGRAM_SEND_MEDIA` (default `1`) enable/disable photo+clip media on initial alert
- `TELEGRAM_MEDIA_CAPTURE_FALLBACK` (default `1`) capture a live frame when no linked snapshot exists
- `TELEGRAM_SEND_CLIP` (default `1`) enable/disable short clip capture and send
- `TELEGRAM_CLIP_SECONDS` (default `4`), `TELEGRAM_CLIP_FPS` (default `6`)
- `TELEGRAM_MEDIA_MAX_BYTES` (default `45000000`) max upload size per media file
- `FIRE_FUSION_WINDOW`, `INTRUDER_FUSION_WINDOW`, `ALERT_COOLDOWN`, `FIRE_COOLDOWN`
- `NODE_OFFLINE_SECONDS`

MQTT:
- `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`
- `MQTT_BROKER_USERNAME`, `MQTT_BROKER_PASSWORD`
- `MQTT_TOPIC_ROOT`
- `MQTT_INGEST_CLIENT_ID`, `MQTT_INGEST_QOS`

Vision:
- `VISION_EVENT_SINK=mqtt|api|db` (recommended: `mqtt`)
- `OUTDOOR_URL`, `INDOOR_URL`
- `UNKNOWN_THRESHOLD`, `UNKNOWN_STREAK`, `FLAME_STREAK`
- `FIRE_RATIO_THRESHOLD`, `FIRE_MIN_BLOB_RATIO`, `FIRE_MIN_HOT_RATIO`

## Firmware

Active sketches are under `firmware/mqtt/`:

- `door_force_mqtt`
- `smoke_node1_mqtt`
- `smoke_node2_mqtt`
- `cam_outdoor_mqtt`
- `cam_indoor_mqtt`

Archived sketches:

- `firmware/archive/espnow/`
- `firmware/archive/legacy_http/`

## Deployment (systemd)

```bash
bash deploy/systemd/prepare_units.sh \
  --project-root /home/pi/projects/CpE-Practice-and-Design \
  --run-user pi \
  --python-bin /home/pi/projects/CpE-Practice-and-Design/.venv/bin/python3

sudo bash deploy/systemd/install_units.sh \
  --generated-dir deploy/systemd/generated \
  --enable-stack \
  --enable-vision \
  --start-now
```

## Documentation

- `docs/README.md`
- `docs/context/CURRENT_STATUS.md`
- `docs/instructions/transport/mqtt_quick_start.md`
- `docs/instructions/transport/mqtt_deployment.md`
- `docs/instructions/camera/dual_esp32cam.md`
- `docs/instructions/deployment/pi_systemd_autostart.md`
