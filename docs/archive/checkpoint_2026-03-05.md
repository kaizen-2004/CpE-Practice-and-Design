# Technical Checkpoint (2026-03-05)

This file is a handoff snapshot so a new AI session can continue implementation without re-discovery.

## 1) System Snapshot

- Project: Local-first condo monitoring thesis prototype.
- Monitored areas:
  - Living Room
  - Door Entrance Area
- Deployed architecture (current):
  - Raspberry Pi 2 hosts Flask app, API, SQLite DB, dashboard, alert notifier.
  - Second-hand laptop runs OpenCV vision runtime (face recognition + flame detection).
  - Sensor transport is HTTP POST + JSON to `POST /api/sensors/event` (no MQTT).

## 2) Hardware + Node IDs

- `mq2_living`: ESP32-C3 + MQ-2 smoke sensor (Living Room)
- `mq2_door`: ESP32-C3 + MQ-2 smoke sensor (Door Entrance Area)
- `door_force`: ESP32-C3 + GY-LSM6DS3 IMU (Door Entrance Area)
- `cam_outdoor`: ESP32-CAM (AI Thinker) for outdoor stream
- `cam_indoor`: logical camera node updated by vision runtime loop

Node metadata lives in:
- `pi/config.py` (`NODE_META`, `NODE_ALIASES`)

## 3) Firmware Status (Arduino IDE)

Firmware folders:
- `firmware/legacy_http/smoke_node1/`
- `firmware/legacy_http/smoke_node2/`
- `firmware/legacy_http/door_force/`
- `firmware/outdoor_camera/`

### 3.1 Smoke nodes (`mq2_living`, `mq2_door`)

- Board target: `ESP32C3 Dev Module`
- Protocol: HTTP POST JSON to `/api/sensors/event`
- Events sent:
  - `SMOKE_HIGH`
  - `SMOKE_NORMAL`
  - `SMOKE_HEARTBEAT`
- Reliability behavior:
  - Wi-Fi reconnect loop
  - pending-event retry queue
  - critical event preemption

### 3.2 Door-force node (`door_force`)

- Board target: `ESP32C3 Dev Module`
- IMU: LSM6DS3 via direct register access (`Wire.h`, no third-party lib)
- Events sent:
  - `DOOR_FORCE`
  - `DOOR_HEARTBEAT`
- Reliability behavior:
  - Wi-Fi reconnect
  - IMU re-init on read failures
  - pending-event retry queue

### 3.3 Outdoor camera (`cam_outdoor`)

- Board target: `AI Thinker ESP32-CAM`
- Exposed endpoints:
  - `http://<ip>:81/stream` (MJPEG)
  - `http://<ip>/capture` (JPEG snapshot)
  - `http://<ip>/snapshot.jpg` (alias)
- Optional backend POST:
  - `CAM_BOOT`
  - `CAM_HEARTBEAT`

### 3.4 Last compile validation (local)

Validated with `arduino-cli` on 2026-03-05:
- `esp32:esp32:esp32c3` -> `firmware/legacy_http/smoke_node1` (success)
- `esp32:esp32:esp32c3` -> `firmware/legacy_http/smoke_node2` (success)
- `esp32:esp32:esp32c3` -> `firmware/legacy_http/door_force` (success)
- `esp32:esp32:esp32cam` -> `firmware/outdoor_camera` (success)

## 4) Backend Contract + Behavior

Main ingest endpoint:
- `POST /api/sensors/event` in `pi/app.py`

Required JSON fields:
- `node`
- `event`

Optional fields:
- `room`
- `value`
- `unit`
- `note`
- `ts`

Behavior:
- Normalizes node IDs via `normalize_node_id()`.
- Persists every accepted event with `create_event(...)`.
- Marks node as online with `update_node_seen(...)`.
- Triggers fusion checks only for:
  - `SMOKE_HIGH` -> `handle_fire_signal(...)`
  - `DOOR_FORCE` -> `handle_intruder_evidence(...)`

Important:
- Firmware supports optional `X-API-KEY` header.
- Backend currently does **not** enforce/validate `X-API-KEY`.

## 5) Fusion/Alert Logic (Current)

Defined in `pi/fusion.py`:

- Fire alert (`FIRE`):
  - Requires recent smoke + flame evidence within `FIRE_FUSION_WINDOW` (default 120s).
  - Flame evidence source expected from vision runtime event:
    - `EVENT_FLAME_SIGNAL` from source `CAM_INDOOR`

- Intruder alert (`INTRUDER`):
  - Requires 2-of-3 evidence within `INTRUDER_FUSION_WINDOW` (default 120s):
    - outdoor unknown face (`UNKNOWN` from `CAM_OUTDOOR`)
    - indoor unknown face (`UNKNOWN` from `CAM_INDOOR`)
    - door force (`DOOR_FORCE`)
  - Suppressed when guest mode is ON.

Cooldown env defaults:
- `FIRE_COOLDOWN=75`
- `ALERT_COOLDOWN=45`

## 6) Vision Runtime (Laptop)

File:
- `pi/vision_runtime.py`

Responsibilities:
- Reads outdoor/indoor camera feeds.
- Face detection + LBPH recognition:
  - logs `UNKNOWN` / `AUTHORIZED` events.
- Flame signal detection (indoor):
  - logs `FLAME_SIGNAL`.
- Writes snapshots for unknown/flame cases.
- Updates camera node health:
  - `update_node_seen("cam_outdoor", note="opencv loop")`
  - `update_node_seen("cam_indoor", note="opencv loop")`

Core image helpers:
- `pi/vision_utils.py`
- `pi/fire_utils.py`

## 7) Camera Preview Routing (Dashboard)

Camera URLs are selected in `pi/app.py` (`/dashboard` route).

Current outdoor/indoor preference:
- Outdoor:
  1. `OUTDOOR_URL` (network camera)
  2. `OUTDOOR_CAM_SOURCE` (local USB capture)
  3. Not connected
- Indoor:
  1. `INDOOR_CAM_SOURCE` (local USB capture)
  2. `INDOOR_URL` (network camera)
  3. Not connected

Recent fix already applied:
- Duplicate local source guard prevents outdoor+indoor from showing the same USB device when both sources are identical.

Current `.env` camera state:
- `OUTDOOR_CAM_SOURCE=none`
- `INDOOR_CAM_SOURCE=/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera-video-index0`
- `OUTDOOR_URL=` (empty; set to ESP32-CAM stream IP when available)

Result:
- Indoor uses local webcam.
- Outdoor stays `Not Connected` until `OUTDOOR_URL` is set.

## 8) Node Online/Offline in Dashboard

Node status is based on `node_status.last_seen_ts`.

Online rule:
- `now - last_seen_ts <= NODE_OFFLINE_SECONDS`
- Default: `NODE_OFFLINE_SECONDS=180`

Implication:
- ESP32-C3 devices are shown connected once they post events or heartbeats.
- If they stop sending for >180s, dashboard marks them offline.

## 9) Data + Storage Paths

- SQLite DB path: `db/thesis.db`
- Snapshots root: `snapshots/`
- Face dataset: `data/faces/`
- Fire dataset:
  - `data/fire/flame/`
  - `data/fire/non_flame/`
- Models:
  - `models/lbph.yml`
  - `models/labels.json`
  - `models/fire_color.json`

Primary DB tables:
- `events`
- `alerts`
- `snapshots`
- `faces`
- `face_samples`
- `node_status`
- `settings`
- `alert_notifications`

## 10) Wiring Documentation

All pin mappings and power notes are in:
- `docs/instructions/hardware_wiring.md`

Includes:
- both MQ-2 nodes
- door-force IMU node
- ESP32-CAM (AI Thinker) pin map and flashing wiring

## 11) Runbook Commands

### 11.1 App

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python pi/init_db.py
python pi/app.py
```

### 11.2 Vision runtime (recommended split-host usage)

```bash
python pi/vision_runtime.py --camera-mode esp32 --outdoor-url http://<ESP32_CAM_IP>:81/stream --indoor-url 0
```

Alternative webcam-only debug:

```bash
python pi/vision_runtime.py --camera-mode webcam --outdoor-url 0 --indoor-url 1
```

### 11.3 Firmware compile checks (CLI)

```bash
arduino-cli compile -b esp32:esp32:esp32c3 firmware/legacy_http/smoke_node1
arduino-cli compile -b esp32:esp32:esp32c3 firmware/legacy_http/smoke_node2
arduino-cli compile -b esp32:esp32:esp32c3 firmware/legacy_http/door_force
arduino-cli compile -b esp32:esp32:esp32cam firmware/outdoor_camera
```

## 12) Known Gaps / Next Technical Tasks

1. Set real `OUTDOOR_URL` in `.env` after ESP32-CAM gets IP (to enable outdoor preview).
2. Decide whether backend should enforce `X-API-KEY` (currently optional header is ignored).
3. Keep vision runtime active on laptop so `cam_indoor`/`cam_outdoor` stay online.
4. Validate long-run outdoor stream stability and restart behavior under Wi-Fi drops.
5. Tune thresholds in each ESP32-C3 node on-site (MQ-2 and door-force) to reduce false positives.

## 13) New Session Bootstrap (copy/paste prompt)

Use this in the next session:

```text
Read /home/steve/projects/CpE-Practice-and-Design/docs/archive/checkpoint_2026-03-05.md first, then AGENTS.md and README.md. Continue from the current technical implementation state without changing thesis Main Objective, Specific Objectives, and Keywords in AGENTS.md.
```
