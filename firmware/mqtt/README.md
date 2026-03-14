# MQTT Firmware Set

Active transport firmware for redesigned architecture.

## Node upload map

1. `firmware/mqtt/door_force_mqtt/door_force_mqtt.ino`
2. `firmware/mqtt/smoke_node1_mqtt/smoke_node1_mqtt.ino`
3. `firmware/mqtt/smoke_node2_mqtt/smoke_node2_mqtt.ino`
4. `firmware/mqtt/cam_outdoor_mqtt/cam_outdoor_mqtt.ino`
5. `firmware/mqtt/cam_indoor_mqtt/cam_indoor_mqtt.ino`

## Libraries

- `PubSubClient`
- `WiFi` (ESP32 core)
- `esp_camera` (ESP32-CAM only)

Install missing MQTT library:

```bash
arduino-cli lib install PubSubClient
```

## Secrets

Each sketch supports two modes:

- preferred: create local `secrets.h` (not committed) with real credentials
- fallback: compile with `secrets.example.h` placeholders for dry-run validation

## Compile Validation

Use the batch compile helper:

```bash
bash firmware/mqtt/compile_all.sh
```
