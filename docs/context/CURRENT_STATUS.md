# Current Project Status (2026-03-10)

This file is the primary status snapshot for new AI sessions.

## 1. System Topology

- Primary host: Raspberry Pi (`pi/app.py`, `pi/mqtt_ingest.py`, SQLite, dashboard, alerts).
- Vision host: Raspberry Pi preferred; laptop supported as fallback using MQTT event publish mode.
- Monitored areas: Living Room and Door Entrance Area.

## 2. Transport Status (Active)

Active architecture:

- Sensor/camera nodes publish MQTT over Wi-Fi.
- Local broker: Mosquitto on Raspberry Pi.
- MQTT ingest service: `pi/mqtt_ingest.py`.
- Backend contract remains `POST /api/sensors/event`.

Data path:

`MQTT publish -> Mosquitto -> pi/mqtt_ingest.py -> POST /api/sensors/event -> Flask + DB + fusion + alerts`

## 3. Firmware Status

Active firmware set is under `firmware/mqtt/`:

- `firmware/mqtt/door_force_mqtt/door_force_mqtt.ino`
- `firmware/mqtt/smoke_node1_mqtt/smoke_node1_mqtt.ino`
- `firmware/mqtt/smoke_node2_mqtt/smoke_node2_mqtt.ino`
- `firmware/mqtt/cam_outdoor_mqtt/cam_outdoor_mqtt.ino`
- `firmware/mqtt/cam_indoor_mqtt/cam_indoor_mqtt.ino`

Archived (not active deployment path):

- `firmware/archive/espnow/...`
- `firmware/archive/legacy_http/...`

## 4. Runtime Entry Points

- Flask backend: `python3 pi/app.py`
- MQTT ingest: `python3 pi/mqtt_ingest.py`
- Vision runtime: `python3 pi/vision_runtime.py --event-sink mqtt ...`

## 5. Deployment Services

Systemd templates:

- `deploy/systemd/templates/thesis-app.service.tmpl`
- `deploy/systemd/templates/thesis-mqtt-ingest.service.tmpl`
- `deploy/systemd/templates/thesis-vision.service.tmpl` (optional)
- `deploy/systemd/templates/thesis-stack.target.tmpl`

Broker deployment:

- `deploy/mosquitto/mosquitto.conf`
- `deploy/mosquitto/acl`

## 6. Documentation Authority

Use these docs in order for implementation guidance:

1. `docs/README.md`
2. `docs/instructions/transport/mqtt_quick_start.md`
3. `docs/instructions/transport/mqtt_deployment.md`
4. `docs/instructions/hardware_wiring.md`
5. `docs/instructions/deployment/pi_systemd_autostart.md`

Archive notes are in `docs/archive/` and are not the primary source of truth.
