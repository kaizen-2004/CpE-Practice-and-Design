# ESP-NOW Quick Start (Offline Checklist)

Use this when internet is unavailable and you need a fast deployment flow.

## 1. Board Roles (4 ESP32 total)

1. `door_force` -> `firmware/door_force_espnow/door_force_espnow.ino`
2. `smoke_node1` -> `firmware/smoke_node1_espnow/smoke_node1_espnow.ino`
3. `smoke_node2` -> `firmware/smoke_node2_espnow/smoke_node2_espnow.ino`
4. `gateway` (USB near Pi) -> `firmware/espnow_gateway/espnow_gateway.ino`

Gateway is not a WiFi AP. It only receives ESP-NOW and forwards to Pi over USB serial.

## 2. Preflight (Run Once)

```bash
pip3 install -r requirements.txt
arduino-cli core list
arduino-cli board list
```

Verify:
- `esp32:esp32` core is installed.
- You can see serial ports (`/dev/ttyACM*` or `/dev/ttyUSB*`).

## 3. Compile (Optional, Recommended)

```bash
mkdir -p .arduino-build/door_force_espnow .arduino-build/smoke_node1_espnow .arduino-build/smoke_node2_espnow .arduino-build/espnow_gateway

arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/door_force_espnow firmware/door_force_espnow
arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/smoke_node1_espnow firmware/smoke_node1_espnow
arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/smoke_node2_espnow firmware/smoke_node2_espnow
arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/espnow_gateway firmware/espnow_gateway
```

## 4. Flash Checklist (Do in this order)

1. Connect target board by USB.
2. Run `arduino-cli board list` and note the port.
3. Upload the matching firmware.
4. Label the board before moving to next board.

Gateway first:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/espnow_gateway firmware/espnow_gateway
```

Door-force:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/door_force_espnow firmware/door_force_espnow
```

Smoke node 1:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/smoke_node1_espnow firmware/smoke_node1_espnow
```

Smoke node 2:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/smoke_node2_espnow firmware/smoke_node2_espnow
```

## 5. Runtime Startup (Every Test Run)

Terminal 1 (Flask):

```bash
python3 pi/app.py
```

Terminal 2 (Gateway serial bridge):

```bash
python3 pi/serial_ingest.py --port /dev/ttyACM0 --baud 115200
```

Then:
1. Keep gateway ESP32 connected to Pi USB.
2. Power ON door-force and smoke nodes.
3. Open dashboard: `http://<pi-ip>:5000/dashboard`

## 6. Pass/Fail Checks

Pass if all are true:
1. Gateway shows: `[GATEWAY] ESP-NOW ready ch=6 ...`
2. Bridge shows `tx_ok` increasing.
3. Dashboard sensor cards update.
4. Door movement triggers `DOOR_FORCE`.
5. Smoke test triggers `SMOKE_HIGH`.

Fail clues:
1. `tx_fail` increasing -> Flask/API path issue.
2. No gateway JSON lines -> channel mismatch or out-of-range nodes.
3. Still seeing `[WiFi] Disconnected reason=2` on node -> wrong (old) firmware flashed.

## 7. Data Path Reminder

`ESP-NOW sensor packet -> gateway serial JSON -> pi/serial_ingest.py -> POST /api/sensors/event -> dashboard`

## 8. Legacy HTTP Firmware Location

If you need to revert to old direct-WiFi HTTP nodes, they are now kept under:

- `firmware/legacy_http/door_force/door_force.ino`
- `firmware/legacy_http/smoke_node1/smoke_node1.ino`
- `firmware/legacy_http/smoke_node2/smoke_node2.ino`
