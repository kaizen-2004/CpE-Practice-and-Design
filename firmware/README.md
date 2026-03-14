# Firmware Upload Map

Use this map to avoid flashing the wrong sketch.

## Active Mode (MQTT over Wi-Fi)

Flash these sketches:

1. Door-force node:
   - `firmware/mqtt/door_force_mqtt/door_force_mqtt.ino`
2. Smoke node 1:
   - `firmware/mqtt/smoke_node1_mqtt/smoke_node1_mqtt.ino`
3. Smoke node 2:
   - `firmware/mqtt/smoke_node2_mqtt/smoke_node2_mqtt.ino`
4. Outdoor camera:
   - `firmware/mqtt/cam_outdoor_mqtt/cam_outdoor_mqtt.ino`
5. Indoor camera:
   - `firmware/mqtt/cam_indoor_mqtt/cam_indoor_mqtt.ino`

Also run on Pi:

- `python3 pi/mqtt_ingest.py`

## Archived Firmware (Not Active Deployment Path)

- ESP-NOW set: `firmware/archive/espnow/`
- Legacy direct HTTP set: `firmware/archive/legacy_http/`

## Full Instructions

- `docs/README.md`
- `docs/instructions/transport/mqtt_quick_start.md`
- `docs/instructions/transport/mqtt_deployment.md`
- `docs/instructions/camera/dual_esp32cam.md`
