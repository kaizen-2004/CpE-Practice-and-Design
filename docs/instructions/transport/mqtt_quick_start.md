# MQTT Quick Start (Offline Checklist)

Use this when you need the fastest MQTT deployment path.

## 1. Board Roles (5 ESP32 total)

1. `door_force` -> `firmware/mqtt/door_force_mqtt/door_force_mqtt.ino`
2. `smoke_node1` -> `firmware/mqtt/smoke_node1_mqtt/smoke_node1_mqtt.ino`
3. `smoke_node2` -> `firmware/mqtt/smoke_node2_mqtt/smoke_node2_mqtt.ino`
4. `cam_outdoor` -> `firmware/mqtt/cam_outdoor_mqtt/cam_outdoor_mqtt.ino`
5. `cam_indoor` -> `firmware/mqtt/cam_indoor_mqtt/cam_indoor_mqtt.ino`

## 2. Preflight

```bash
pip3 install -r requirements.txt
sudo apt install -y mosquitto mosquitto-clients
arduino-cli core list
arduino-cli board list
```

Verify:
- `esp32:esp32` core is installed
- MQTT broker is running on Pi (`systemctl status mosquitto`)

## 3. Firmware Secrets

For each sketch folder:
1. Copy `secrets.example.h` -> `secrets.h`
2. Set:
   - `WIFI_SSID`, `WIFI_PASSWORD`
   - `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`
   - `MQTT_USERNAME`, `MQTT_PASSWORD`
   - `MQTT_TOPIC_ROOT` (default: `thesis/v1`)

Compile-only validation can run even without `secrets.h` because the sketches fall back to `secrets.example.h`.

Batch compile all MQTT sketches:

```bash
bash firmware/mqtt/compile_all.sh
```

## 4. Runtime Startup (Every Test Run)

Terminal 1 (Flask):

```bash
python3 pi/app.py
```

Terminal 2 (MQTT ingest):

```bash
python3 pi/mqtt_ingest.py
```

Terminal 3 (vision runtime):

```bash
python3 pi/vision_runtime.py --event-sink mqtt --camera-mode esp32 \
  --outdoor-url http://OUTDOOR_IP:81/stream \
  --indoor-url http://INDOOR_IP:81/stream
```

## 5. Data Path Reminder

`sensor/camera node -> MQTT publish -> Mosquitto -> pi/mqtt_ingest.py -> POST /api/sensors/event -> Flask`

## 6. Pass/Fail Checks

Pass if all are true:
1. `mqtt_ingest` prints subscribed topic filters and increasing `ok=` counter.
2. Dashboard updates node health and events.
3. Door movement triggers `DOOR_FORCE`.
4. Smoke test triggers `SMOKE_HIGH`.
5. Vision runtime publishes `UNKNOWN`/`AUTHORIZED`/`FLAME_SIGNAL`.

Fail clues:
1. `mqtt_ingest` `dropped_parse` increases -> payload format mismatch.
2. broker rejects node -> MQTT auth/ACL issue.
3. `forward_fail` increases -> Flask/API path issue.
