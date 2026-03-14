# Outdoor Camera Firmware (`cam_outdoor`) - Arduino IDE

## Board + Libraries
- Board: `AI Thinker ESP32-CAM` (Arduino core for ESP32 by Espressif)
- Built-in libraries used: `esp_camera`, `esp_http_server`, `WiFi.h`, `HTTPClient.h`
- No third-party library required.

## Files
- `outdoor_camera.ino`

## Exactly what to edit before upload
Open `outdoor_camera.ino` and edit:

- Wi-Fi:
  - `WIFI_SSID`
  - `WIFI_PASSWORD`
  - `WIFI_HOSTNAME`
- Identity:
  - `NODE_ID` (default `cam_outdoor`)
  - `ROOM_NAME` (default `Door Entrance Area`)
- Optional backend heartbeat POST:
  - `BACKEND_EVENT_URL` (empty string disables POST)
  - `API_KEY` (optional `X-API-KEY`)
- Camera tuning:
  - `CAMERA_FRAME_SIZE` (`FRAMESIZE_QVGA`, `FRAMESIZE_VGA`, `FRAMESIZE_SVGA`, ...)
  - `CAMERA_JPEG_QUALITY`
  - `STREAM_FRAME_DELAY_MS`

## Upload steps (Arduino IDE)
1. `Tools -> Board -> ESP32 Arduino -> AI Thinker ESP32-CAM`
2. Set correct port (USB-TTL adapter).
3. Put board in flash mode: `GPIO0 -> GND`, then reset/power cycle.
4. Upload sketch.
5. Remove `GPIO0 -> GND`, then reset/power cycle.
6. Open Serial Monitor at `115200`.

## URLs after boot
- MJPEG stream: `http://<camera-ip>:81/stream`
- Snapshot: `http://<camera-ip>/capture`
- Snapshot alias: `http://<camera-ip>/snapshot.jpg`
- Landing page: `http://<camera-ip>/`

Use stream URL in your vision runtime:

```bash
python pi/vision_runtime.py --camera-mode esp32 --outdoor-url http://<camera-ip>:81/stream
```

## How it works (short)
- Initializes OV2640 camera (AI Thinker pin map).
- Starts two HTTP servers:
  - port `80` for control/snapshot endpoints
  - port `81` for MJPEG stream endpoint
- On Wi-Fi drop, server stops and auto-restores after reconnect.
- Optionally posts `CAM_BOOT` and periodic `CAM_HEARTBEAT` to your backend `/api/sensors/event`.

## Error handling + reconnect
- Wi-Fi reconnect loop retries every `WIFI_RETRY_INTERVAL_MS`.
- If Wi-Fi disconnects, camera servers are stopped cleanly.
- Failed heartbeat/event POSTs are queued and retried.
- Camera init failure triggers reboot.

## Wiring reference
See `../hardware_wiring.md`, section:
- `4) Outdoor camera node (cam_outdoor)`
