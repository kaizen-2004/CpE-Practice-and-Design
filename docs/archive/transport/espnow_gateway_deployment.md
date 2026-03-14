# ESP-NOW + Gateway Deployment Guide

This guide is the updated sensor transport for your thesis system:

- Sensor nodes use **ESP-NOW** (no router login/password on sensor nodes).
- One gateway ESP32 (USB near Pi) forwards sensor events to Flask via serial bridge.
- Flask API path remains the same: `POST /api/sensors/event`.

Need a condensed checklist? See `espnow_quick_start.md`.

## 1. Hardware Roles

If you have all three sensor nodes active, you need **4 ESP32 boards total**:

1. `door_force` board: flash `firmware/door_force_espnow/door_force_espnow.ino`
2. `smoke_node1` board: flash `firmware/smoke_node1_espnow/smoke_node1_espnow.ino`
3. `smoke_node2` board: flash `firmware/smoke_node2_espnow/smoke_node2_espnow.ino`
4. `gateway` board (near Raspberry Pi): flash `firmware/espnow_gateway/espnow_gateway.ino`

The gateway is **not** a WiFi AP/router. It only receives ESP-NOW and outputs serial JSON.

## 2. Updated Data Flow

```text
Door-force + Smoke nodes
        |
        |  ESP-NOW (channel 6)
        v
Gateway ESP32 (USB to Pi)
        |
        |  Serial JSON lines @115200
        v
pi/serial_ingest.py
        |
        |  HTTP POST /api/sensors/event
        v
Flask app + DB + Dashboard
```

## 3. Source Files

- `firmware/door_force_espnow/door_force_espnow.ino`
- `firmware/smoke_node1_espnow/smoke_node1_espnow.ino`
- `firmware/smoke_node2_espnow/smoke_node2_espnow.ino`
- `firmware/espnow_gateway/espnow_gateway.ino`
- `pi/serial_ingest.py`
- `firmware/common/espnow_packet.h`

## 4. Pre-Implementation Checklist

1. Install Python deps once:

```bash
pip3 install -r requirements.txt
```

2. Confirm board package exists:

```bash
arduino-cli core list
```

3. Confirm serial ports before upload:

```bash
arduino-cli board list
```

4. Keep all ESP-NOW sketches on the same channel (default already `6`).

## 5. Build Commands (Optional but Recommended)

Use workspace-local build paths to avoid permission issues:

```bash
mkdir -p .arduino-build/door_force_espnow .arduino-build/smoke_node1_espnow .arduino-build/smoke_node2_espnow .arduino-build/espnow_gateway

arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/door_force_espnow firmware/door_force_espnow
arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/smoke_node1_espnow firmware/smoke_node1_espnow
arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/smoke_node2_espnow firmware/smoke_node2_espnow
arduino-cli compile --fqbn esp32:esp32:esp32c3 --build-path .arduino-build/espnow_gateway firmware/espnow_gateway
```

## 6. Flash Order (Step-by-Step)

Repeat the upload step for each physical board by changing `-p <port>`.

1. Flash gateway board first:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/espnow_gateway firmware/espnow_gateway
```

2. Flash door-force node:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/door_force_espnow firmware/door_force_espnow
```

3. Flash smoke node 1:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/smoke_node1_espnow firmware/smoke_node1_espnow
```

4. Flash smoke node 2:

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c3 --input-dir .arduino-build/smoke_node2_espnow firmware/smoke_node2_espnow
```

## 7. Runtime Startup Order

Do this every test run:

1. Connect gateway ESP32 to Raspberry Pi via USB.
2. Start Flask:

```bash
python3 pi/app.py
```

3. In another terminal, start bridge:

```bash
python3 pi/serial_ingest.py --port /dev/ttyACM0 --baud 115200
```

4. Power sensor nodes.
5. Open dashboard:

```text
http://<pi-ip>:5000/dashboard
```

## 8. What "Healthy" Logs Look Like

Gateway serial:

```text
[BOOT] ESP-NOW gateway start
[GATEWAY] ESP-NOW ready ch=6 local_mac=...
{"node":"door_force","event":"DOOR_FORCE",...}
```

Bridge terminal:

```text
[bridge] listening on /dev/ttyACM0@115200, forwarding to http://127.0.0.1:5000/api/sensors/event
[bridge] status rx_lines=... rx_events=... tx_ok=... tx_fail=... pending=0 bad_lines=0
```

Door-force node serial:

```text
[BOOT] Door-force ESP-NOW node start
[ESPNOW] ready ch=6 mode=broadcast local_mac=...
[ESPNOW] DOOR_HEARTBEAT sent seq=...
```

## 9. Troubleshooting

1. No events in dashboard:
   - Verify `pi/app.py` and `pi/serial_ingest.py` are both running.
   - Verify bridge `--port` matches gateway USB port.

2. Node says ESP-NOW ready but no packets received:
   - Ensure node and gateway use same `ESPNOW_CHANNEL`.
   - Move nodes closer to gateway for testing.
   - Power-cycle gateway after flashing all boards.

3. `tx_fail` grows in bridge:
   - Flask is unreachable or API errors; check Flask terminal for route errors.
   - Confirm endpoint exists: `POST /api/sensors/event`.

4. Old WiFi disconnect errors (`reason=2`) still appear:
   - That means old WiFi-based firmware is still flashed.
   - Reflash the board with `*_espnow.ino`.

## 10. Why This Removes WiFi Headaches

- Sensor nodes do not do AP authentication/reconnect loops.
- No SSID/password mismatch on each remote node.
- Only one USB-connected gateway talks to your server process.
- Your existing Flask dashboard and alert pipeline stay unchanged.
