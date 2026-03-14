# cam_indoor_mqtt

ESP32-CAM indoor firmware with:
- HTTP MJPEG stream (`:81/stream`)
- MQTT status/events/control/ack

## Setup

1. Copy `firmware/mqtt/cam_indoor_mqtt/secrets.example.h` to `firmware/mqtt/cam_indoor_mqtt/secrets.h`.
2. Set Wi-Fi/MQTT credentials in `secrets.h`.
3. Flash to indoor ESP32-CAM.
4. Verify status topic `thesis/v1/status/cam_indoor`.

For compile-only dry runs, `secrets.h` is optional; the sketch falls back to `secrets.example.h`.
