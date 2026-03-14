# Dual ESP32-CAM Integration (Indoor + Outdoor)

This project uses two ESP32-CAM nodes:

- `cam_outdoor` for Door Entrance Area
- `cam_indoor` for Living Room

## 1. Firmware

- Outdoor: `firmware/mqtt/cam_outdoor_mqtt/cam_outdoor_mqtt.ino`
- Indoor: `firmware/mqtt/cam_indoor_mqtt/cam_indoor_mqtt.ino`

Each camera sketch provides:

- HTTP MJPEG stream (`:81/stream`)
- HTTP snapshot endpoint (`/capture`)
- MQTT status/events/control

## 2. Vision Runtime Consumption

Recommended startup:

```bash
python3 pi/vision_runtime.py --event-sink mqtt --camera-mode esp32 \
  --outdoor-url http://OUTDOOR_IP:81/stream \
  --indoor-url http://INDOOR_IP:81/stream
```

Vision runtime publishes:

- `UNKNOWN`
- `AUTHORIZED`
- `FLAME_SIGNAL`

to MQTT topics under `thesis/v1/events/cam_outdoor` and `thesis/v1/events/cam_indoor`.

## 3. Why MQTT Is Not Used for Video

Video frames remain HTTP MJPEG because:

1. ESP32-CAM resources are limited for broker-style frame transport.
2. MQTT is optimal here for control/status/events, not bulk video transport.
3. HTTP stream keeps latency lower and integration simpler on current hardware.

## 4. Optional MQTT Camera Control

Control topics:

- `thesis/v1/camera/cam_outdoor/control`
- `thesis/v1/camera/cam_indoor/control`

Supported command examples:

- `status`
- `flash_on`
- `flash_off`
- `reboot`
