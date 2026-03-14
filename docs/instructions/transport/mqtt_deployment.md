# MQTT Deployment Guide

This guide defines the active wireless sensor transport:

- Sensor/camera nodes use Wi-Fi + MQTT.
- Local MQTT broker runs on Raspberry Pi (Mosquitto).
- `pi/mqtt_ingest.py` consumes topics and forwards to Flask `POST /api/sensors/event`.

## 1. Architecture

```text
ESP32 nodes/cameras -> MQTT publish -> Mosquitto (Pi) -> pi/mqtt_ingest.py -> Flask API -> DB/fusion/dashboard
```

## 2. Topic Namespace

Topic root: `thesis/v1`

- Events: `thesis/v1/events/<node>`
- Status: `thesis/v1/status/<node>`
- Camera control: `thesis/v1/camera/<node>/control`
- Camera ack: `thesis/v1/camera/<node>/ack`

## 3. Broker Setup

Use files in:

- `deploy/mosquitto/mosquitto.conf`
- `deploy/mosquitto/acl`
- `deploy/mosquitto/README.md`

## 4. Node IDs

Supported IDs:

- `mq2_living`
- `mq2_door`
- `door_force`
- `cam_outdoor`
- `cam_indoor`

## 5. Payload Contract (Compact JSON)

Event payload example:

```json
{"v":1,"e":"SMOKE_HIGH","x":2240,"u":"adc","q":1021,"m":"threshold_crossed","room":"Living Room"}
```

Status payload example:

```json
{"v":1,"s":1,"r":-62,"q":1022,"m":"latched=0"}
```

## 6. QoS + Retain Policy

Current firmware stack uses `PubSubClient` on ESP32 nodes/cameras.

- Sensor/camera `publish(...)` packets are QoS 0 with app-level retry/sequence handling.
- LWT (last will) QoS is configurable in `connect(...)` and currently:
  - `door_force`: QoS 2
  - `cam_indoor`, `cam_outdoor`: QoS 2
  - `smoke_node1`, `smoke_node2`: QoS 1

Recommended retained-message policy:

- Retain `status/<node>`: **YES** (online/offline + latest state)
- Retain `events/<node>`: **NO** (avoid replaying stale alarms on subscribe/restart)
- Retain `camera/<node>/control`: **NO** for one-shot commands
- Retain `camera/<node>/ack`: **NO**

If strict per-message publish QoS 1/2 is required for event topics, migrate ESP firmware from `PubSubClient` to an MQTT client library that supports QoS 1/2 publish flows.

## 7. Bridge Runtime

Run ingest service:

```bash
python3 pi/mqtt_ingest.py \
  --broker-host 127.0.0.1 \
  --broker-port 1883 \
  --topic-root thesis/v1 \
  --api-url http://127.0.0.1:5000/api/sensors/event
```

## 8. Systemd Deployment

Generate and install units:

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

## 9. Validation Commands

Publish test event:

```bash
mosquitto_pub -h 127.0.0.1 -p 1883 -u mq2_living -P '<pass>' \
  -t thesis/v1/events/mq2_living \
  -m '{"v":1,"e":"SMOKE_HIGH","x":2300,"u":"adc","q":1}'
```

Observe ingest:

```bash
journalctl -u thesis-mqtt-ingest.service -f
```

## 10. Legacy Archive

ESP-NOW and direct HTTP node firmware are archived under:

- `firmware/archive/espnow/`
- `firmware/archive/legacy_http/`

They are not part of the active deployment path.
