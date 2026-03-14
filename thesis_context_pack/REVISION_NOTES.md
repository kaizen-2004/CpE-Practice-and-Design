# Revision Notes (2026-03-04)

This revision reflects the latest implementation architecture and current deliverables.

## Key updates (current implementation)
- **Server host platform:** Raspberry Pi **2** (Flask dashboard, API, SQLite logging, and alert lifecycle).
- **Vision processing host:** **Second-hand laptop** for face recognition and visual flame detection algorithms/runtime.
- **Monitoring scope:** **2 areas** for controlled testing and demo:
  - **Living Room**
  - **Door Entrance Area**
- **Cameras (2 total):**
  - **Indoor:** USB **UVC webcam** (local capture source).
  - **Outdoor:** **ESP32-CAM** on the same Wi-Fi/LAN, sending **MJPEG over HTTP** (dashboard may use periodic JPEG snapshots).
  - **Night-vision support:** IR illumination LEDs for both cameras.
- **Smoke/door sensing nodes:** **3x ESP32-C3**
  - `mq2_living` for Living Room smoke events
  - `mq2_door` for Door Entrance Area smoke events
  - `door_force` for forced-entry sensing using **GY-LSM6DS3**
- **Removed hardware path:** MCP3008 ADC (no longer part of implementation).
- **Sensor uplink protocol:** **HTTP POST + JSON** to `POST /api/sensors/event` (no MQTT).

## Current software deliverables reflected in this pack
- Local-first dashboard, history/events pages, ACK workflow, snapshots, and summaries.
- LBPH face dataset capture/training/retrain flow with runtime model reload.
- Fusion logic implemented:
  - **INTRUDER:** two-of-three evidence (outdoor unknown, indoor unknown, door-force).
  - **FIRE:** flame + smoke evidence within fusion window.
- Flame false-positive filtering refinements (ratio + blob + hot-core checks).
- Persistent Telegram alerting/reminder flow (optional remote channel).

> Note: Chapter 1 and Chapter 3 implementation-focused sections were synchronized to this architecture to avoid conflicting hardware descriptions in future AI sessions.
