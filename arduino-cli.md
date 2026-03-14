# Arduino CLI Commands

Run commands from project root:

```bash
cd /home/steve/projects/CpE-Practice-and-Design
```

This file is the quick command reference for the current firmware layout:

- Preferred sensor transport: ESP-NOW sensor nodes + ESP-NOW gateway
- Outdoor camera: independent ESP32-CAM HTTP stream node
- Legacy direct-WiFi sensor sketches: kept only as fallback

## 1) Board-to-sketch map

Current recommended deployment:

- `firmware/door_force_espnow` -> ESP32-C3 door-force node
- `firmware/smoke_node1_espnow` -> ESP32-C3 smoke node 1
- `firmware/smoke_node2_espnow` -> ESP32-C3 smoke node 2
- `firmware/espnow_gateway` -> ESP32-C3 gateway near Raspberry Pi
- `firmware/outdoor_camera` -> AI Thinker ESP32-CAM outdoor stream

Optional utility / fallback sketches:

- `firmware/wifi_diag` -> Wi-Fi troubleshooting sketch
- `firmware/legacy_http/door_force` -> old Wi-Fi HTTP door-force node
- `firmware/legacy_http/smoke_node1` -> old Wi-Fi HTTP smoke node 1
- `firmware/legacy_http/smoke_node2` -> old Wi-Fi HTTP smoke node 2

## 2) One-time setup

```bash
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli board list
arduino-cli core list | rg esp32
```

If you want to inspect supported board names:

```bash
arduino-cli board listall | rg 'esp32c3|esp32cam|AI Thinker'
```

## 3) Common variables

Set these each time before compile or upload:

```bash
PORT=/dev/ttyACM0
FQBN_C3=esp32:esp32:esp32c3
FQBN_CAM=esp32:esp32:esp32cam
BAUD=115200
```

If you are flashing multiple boards in one session, change only `PORT` as you reconnect each device.

## 4) Build folders

Use workspace-local build folders to keep outputs organized:

```bash
mkdir -p \
  .arduino-build/door_force_espnow \
  .arduino-build/smoke_node1_espnow \
  .arduino-build/smoke_node2_espnow \
  .arduino-build/espnow_gateway \
  .arduino-build/outdoor_camera \
  .arduino-build/wifi_diag \
  .arduino-build/legacy_door_force \
  .arduino-build/legacy_smoke_node1 \
  .arduino-build/legacy_smoke_node2
```

## 5) Compile + upload (preferred ESP-NOW sensor stack)

### door_force_espnow

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/door_force_espnow firmware/door_force_espnow
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/door_force_espnow firmware/door_force_espnow
```

### smoke_node1_espnow

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/smoke_node1_espnow firmware/smoke_node1_espnow
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/smoke_node1_espnow firmware/smoke_node1_espnow
```

### smoke_node2_espnow

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/smoke_node2_espnow firmware/smoke_node2_espnow
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/smoke_node2_espnow firmware/smoke_node2_espnow
```

### espnow_gateway

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/espnow_gateway firmware/espnow_gateway
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/espnow_gateway firmware/espnow_gateway
```

Recommended flash order:

1. `firmware/espnow_gateway`
2. `firmware/door_force_espnow`
3. `firmware/smoke_node1_espnow`
4. `firmware/smoke_node2_espnow`

## 6) Compile + upload (outdoor ESP32-CAM)

Before flashing `firmware/outdoor_camera/outdoor_camera.ino`, edit the constants inside the sketch:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `WIFI_HOSTNAME`
- `NODE_ID`
- `ROOM_NAME`
- `BACKEND_EVENT_URL`
- `API_KEY`

Compile and upload:

```bash
arduino-cli compile --fqbn "$FQBN_CAM" --build-path .arduino-build/outdoor_camera firmware/outdoor_camera
arduino-cli upload -p "$PORT" --fqbn "$FQBN_CAM" --input-dir .arduino-build/outdoor_camera firmware/outdoor_camera
```

Important for ESP32-CAM flashing:

- Put `GPIO0` to `GND` during flashing.
- Reset or power-cycle before upload.
- Remove `GPIO0 -> GND` after upload, then reset again.

Useful runtime URL after boot:

```text
http://<camera-ip>:81/stream
```

Example vision runtime command:

```bash
python3 pi/vision_runtime.py --camera-mode esp32 --outdoor-url http://<camera-ip>:81/stream
```

## 7) Compile + upload (`wifi_diag`)

Use this only when troubleshooting Wi-Fi behavior on ESP32 boards.

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/wifi_diag firmware/wifi_diag
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/wifi_diag firmware/wifi_diag
```

## 8) Compile + upload (legacy HTTP fallback)

Use these only if you intentionally want to revert from ESP-NOW back to direct Wi-Fi HTTP sensor nodes.

### legacy door_force

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/legacy_door_force firmware/legacy_http/door_force
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/legacy_door_force firmware/legacy_http/door_force
```

### legacy smoke_node1

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/legacy_smoke_node1 firmware/legacy_http/smoke_node1
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/legacy_smoke_node1 firmware/legacy_http/smoke_node1
```

### legacy smoke_node2

```bash
arduino-cli compile --fqbn "$FQBN_C3" --build-path .arduino-build/legacy_smoke_node2 firmware/legacy_http/smoke_node2
arduino-cli upload -p "$PORT" --fqbn "$FQBN_C3" --input-dir .arduino-build/legacy_smoke_node2 firmware/legacy_http/smoke_node2
```

For legacy HTTP sketches, edit the Wi-Fi and backend constants in the source before compile/upload.

## 9) Serial monitor

Open serial output:

```bash
arduino-cli monitor -p "$PORT" -c baudrate="$BAUD"
```

Monitor for a fixed duration:

```bash
timeout 20s arduino-cli monitor -p "$PORT" -c baudrate="$BAUD"
```

Expected useful logs:

- Gateway: `[GATEWAY] ESP-NOW ready ch=6 ...`
- Door-force node: `[ESPNOW] DOOR_HEARTBEAT sent ...`
- Camera: Wi-Fi connection + IP + HTTP server startup

## 10) Raspberry Pi runtime commands

For the preferred ESP-NOW path, start both services:

```bash
python3 pi/app.py
python3 pi/serial_ingest.py --port /dev/ttyACM0 --baud 115200
```

If the gateway is on another port:

```bash
python3 pi/serial_ingest.py --port /dev/ttyUSB0 --baud 115200
```

Bridge target defaults to:

```text
http://127.0.0.1:5000/api/sensors/event
```

Optional custom bridge example:

```bash
python3 pi/serial_ingest.py \
  --port /dev/ttyACM0 \
  --baud 115200 \
  --server-url http://127.0.0.1:5000/api/sensors/event
```

## 11) Fast validation flow

After flashing the recommended stack:

1. Keep the gateway connected to the Raspberry Pi by USB.
2. Start Flask: `python3 pi/app.py`
3. Start bridge: `python3 pi/serial_ingest.py --port /dev/ttyACM0 --baud 115200`
4. Power the door-force and smoke nodes.
5. Open `http://<pi-ip>:5000/dashboard`

Healthy signs:

- Gateway prints JSON lines for sensor packets.
- Bridge shows `tx_ok` increasing.
- Dashboard sensor cards update.
- Door movement creates `DOOR_FORCE`.
- Smoke test creates `SMOKE_HIGH`.

## 12) Useful troubleshooting commands

Detect boards and ports:

```bash
arduino-cli board list
```

Check which process is using a serial port:

```bash
lsof /dev/ttyACM0
```

Compile-check only:

```bash
arduino-cli compile --fqbn "$FQBN_C3" firmware/door_force_espnow
arduino-cli compile --fqbn "$FQBN_CAM" firmware/outdoor_camera
```

Show installed ESP32 core:

```bash
arduino-cli core list | rg esp32
```

List all available serial devices:

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

## 13) Important notes

- Preferred current sensor transport is ESP-NOW.
- Legacy HTTP sketches are kept under `firmware/legacy_http/`.
- `firmware/outdoor_camera` is independent from the ESP-NOW sensor transport.
- Use one serial consumer at a time: close `monitor` before `upload`.
- The gateway and `pi/serial_ingest.py` must use the same USB port.
