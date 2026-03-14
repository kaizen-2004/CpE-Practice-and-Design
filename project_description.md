# 1. Executive Design Decision Summary

- Wireless transport is now MQTT-over-Wi-Fi only for active deployment. ESP-NOW and serial ingest are archived, not part of runtime.
- Flask remains the application layer (`pi/app.py`) for dashboard, APIs, fusion-trigger entrypoint, alert workflows, and persistence integration.
- SQLite remains the database for events, alerts, snapshots, node health, and notification logs.
- MQTT broker choice is Mosquitto on Raspberry Pi because it is lightweight, stable, easy to operate with systemd, and fits local-first LAN use.
- MQTT subscriber stays in a separate long-running process (`pi/mqtt_ingest.py`) instead of embedding in Flask, to isolate failure domains and keep web app lifecycle simple.
- Two ESP32-CAM nodes are active in redesign:
  - `cam_outdoor` (Door Entrance Area)
  - `cam_indoor` (Living Room)
- Video is transported by HTTP MJPEG stream from ESP32-CAM. MQTT carries camera status/control/acks and semantic events, not video frames.
- Event names are preserved:
  - Intruder: `UNKNOWN`, `AUTHORIZED`, `DOOR_FORCE`
  - Fire: `FLAME_SIGNAL`, `SMOKE_HIGH`, `SMOKE_NORMAL`
- Fusion intent and behavior are preserved:
  - `FIRE` = recent `SMOKE_HIGH` + recent indoor `FLAME_SIGNAL` within fusion window.
  - `INTRUDER` = any 2-of-3: outdoor unknown, indoor unknown, door-force.
  - Door-force-only still falls back to `DOOR_FORCE` alert behavior.

# 2. Recommended Revised Architecture

## 2.1 Logical Components

- Edge sensing nodes (ESP32-C3):
  - `mq2_living`: MQ-2 smoke node (Living Room)
  - `mq2_door`: MQ-2 smoke node (Door Entrance Area)
  - `door_force`: door-force node
- Edge camera nodes (ESP32-CAM):
  - `cam_outdoor`: outdoor stream + MQTT status/control
  - `cam_indoor`: indoor stream + MQTT status/control
- Broker:
  - Mosquitto service on Raspberry Pi
- Ingest bridge:
  - `pi/mqtt_ingest.py`: MQTT subscribe, payload normalization, API forward/retry/dedupe
  - `pi/mqtt_schema.py`: compact payload parsing and topic normalization
- Application backend:
  - `pi/app.py`: `/api/sensors/event`, UI routes, API routes, fusion trigger bridge
  - `pi/fusion.py`: `FIRE`, `INTRUDER`, `DOOR_FORCE` logic
  - `pi/notifications.py`: Telegram notifier
  - `pi/db.py`: SQLite access layer
- Vision runtime:
  - `pi/vision_runtime.py`: consumes ESP32-CAM MJPEG streams, emits `UNKNOWN` / `AUTHORIZED` / `FLAME_SIGNAL` via MQTT (default sink), with API/DB fallback modes.

## 2.2 Data Responsibility Split

- MQTT layer: message transport, decoupled producer/consumer.
- Ingest layer: protocol contract adaptation MQTT -> Flask API payload.
- Flask layer: persistence, fusion invocation, alerts, dashboard serving.
- Vision layer: high-CPU inference loop and semantic event production.

# 3. Broker and Service Layout Decision

## 3.1 Broker Choice

- Selected broker: Mosquitto.
- Why:
  - Native fit for Raspberry Pi resources.
  - Simple ACL and password-file auth.
  - Mature with systemd integration.
  - Sufficient for LAN scale of 5 edge devices + 2 backend clients.

## 3.2 Service Layout

- Keep Flask and MQTT ingest as separate services.
- Final service set on Pi:
  - `mosquitto.service`
  - `thesis-app.service`
  - `thesis-mqtt-ingest.service`
  - optional `thesis-vision.service`
- Justification for separate ingest service:
  - Prevents MQTT reconnect/backoff concerns from coupling into request/response web server lifecycle.
  - Enables isolated restart and log inspection for transport failures.
  - Preserves Flask as an application/API component rather than a message-bus daemon.

# 4. Updated Text Architecture Diagram

```text
            +------------------- LAN Wi-Fi -------------------+
            |                                                 |
            |  ESP32-C3 nodes publish compact MQTT payloads   |
            |  - mq2_living   - mq2_door   - door_force      |
            |  ESP32-CAM nodes publish status/control ACK     |
            |  - cam_outdoor  - cam_indoor                   |
            +---------------------------+---------------------+
                                        |
                                        v
                               +------------------+
                               | Mosquitto Broker |
                               |   (Raspberry Pi) |
                               +---------+--------+
                                         |
                                subscribed topics
                                         |
                                         v
                            +------------------------+
                            | pi/mqtt_ingest.py      |
                            | parse + dedupe + retry |
                            +-----------+------------+
                                        |
                                        v
                         POST /api/sensors/event (Flask)
                                        |
                +-----------------------+------------------------+
                |                                                |
                v                                                v
      +---------------------+                         +----------------------+
      | SQLite (pi/db.py)   |                         | Fusion (pi/fusion.py)|
      | events/alerts/health|                         | FIRE / INTRUDER /    |
      +----------+----------+                         | DOOR_FORCE behavior   |
                 |                                    +-----------+----------+
                 v                                                |
      +----------------------+                                    v
      | Dashboard + History  |                          +---------------------+
      | (Flask templates/API)|                          | Telegram notifier   |
      +----------------------+                          +---------------------+

Video Path (separate from MQTT):
ESP32-CAM HTTP MJPEG -> pi/vision_runtime.py -> MQTT semantic events/status -> mqtt_ingest -> Flask API
```

# 5. Communication Flow

## 5.1 Smoke Event Flow (`SMOKE_HIGH` / `SMOKE_NORMAL`)

1. `mq2_living` or `mq2_door` samples ADC.
2. Node publishes compact event to `thesis/v1/events/<node>`.
3. `pi/mqtt_ingest.py` receives, normalizes payload, forwards to `POST /api/sensors/event`.
4. Flask stores event in SQLite and updates node health.
5. On `SMOKE_HIGH`, Flask invokes `handle_fire_signal(...)`.
6. Fusion checks for recent indoor `FLAME_SIGNAL`. If present, creates `FIRE` alert.
7. Dashboard/history updates and Telegram pipeline handles alert notifications.

## 5.2 Door-Force Flow (`DOOR_FORCE`)

1. `door_force` detects impact score and publishes event.
2. Ingest forwards event to Flask.
3. Flask persists event, updates node health, calls `handle_door_force_signal(...)`.
4. Fusion first checks 2-of-3 intruder condition.
5. If intruder condition is not met, creates fallback `DOOR_FORCE` alert (cooldown-controlled).

## 5.3 Camera/Vision Flow (`UNKNOWN`, `AUTHORIZED`, `FLAME_SIGNAL`)

1. `pi/vision_runtime.py` pulls MJPEG streams from both ESP32-CAM URLs.
2. Runtime performs face/flame inference and emits semantic MQTT events.
3. Ingest forwards semantic events to Flask endpoint.
4. Flask stores events and invokes fusion for:
  - `UNKNOWN` -> `handle_intruder_evidence(...)`
  - `FLAME_SIGNAL` -> `handle_fire_signal(...)`
5. Resulting alerts appear in dashboard/history and trigger Telegram notifications.

## 5.4 Status/Heartbeat Flow

1. Nodes publish status payloads to `thesis/v1/status/<node>`.
2. Ingest maps to heartbeat event types (`SMOKE_HEARTBEAT`, `DOOR_HEARTBEAT`, `CAM_HEARTBEAT`, `NODE_HEARTBEAT`).
3. Flask records heartbeat event and refreshes `node_status` timestamps.
4. Dashboard shows online/offline state based on `NODE_OFFLINE_SECONDS`.

# 6. MQTT Topic Hierarchy

Base root: `thesis/v1`

- Events (all sensor/vision semantic events):
  - `thesis/v1/events/mq2_living`
  - `thesis/v1/events/mq2_door`
  - `thesis/v1/events/door_force`
  - `thesis/v1/events/cam_outdoor`
  - `thesis/v1/events/cam_indoor`
- Status/heartbeat:
  - `thesis/v1/status/<node_id>`
- Camera control plane:
  - `thesis/v1/camera/<node_id>/control`
  - `thesis/v1/camera/<node_id>/ack`

Subscriber filters in ingest:

- `thesis/v1/events/+`
- `thesis/v1/status/+`
- `thesis/v1/camera/+/ack`

# 7. Compact MQTT Payload Design

## 7.1 Common Compact Fields

- `v` (int): payload schema version, currently `1`
- `e` (string): event name
- `x` (number): numeric value (ADC, score, ratio)
- `u` (string): value unit
- `q` (int): sequence number for dedupe/replay tracing
- `t` (int): unix timestamp seconds (optional; ingest auto-fills if missing)
- `m` (string): compact note/metadata
- `room` (string): optional room override

## 7.2 Smoke Event Payload

Example `SMOKE_HIGH`:

```json
{"v":1,"e":"SMOKE_HIGH","x":2310,"u":"adc","q":22}
```

Example `SMOKE_NORMAL`:

```json
{"v":1,"e":"SMOKE_NORMAL","x":1840,"u":"adc","q":23}
```

## 7.3 Door-Force Payload

```json
{"v":1,"e":"DOOR_FORCE","x":1.82,"u":"score","q":77,"m":"d=0.41,g=117"}
```

## 7.4 Heartbeat / Status Payload

```json
{"v":1,"s":1,"r":-60,"q":103,"m":"online"}
```

Field meanings:

- `s`: online flag (`1` online, `0` offline or degraded)
- `r`: RSSI dBm (if available)

## 7.5 Camera Status and Optional Control ACK

Camera status to `status/<node>`:

```json
{"v":1,"s":1,"r":-58,"q":211,"m":"mjpeg_ready"}
```

Camera ack to `camera/<node>/ack`:

```json
{"v":1,"ok":1,"q":212,"m":"flash_on"}
```

Optional control payload to `camera/<node>/control`:

```json
{"v":1,"cmd":"flash_on","q":213}
```

Supported control commands (practical minimum):

- `status`
- `reboot`
- `flash_on`
- `flash_off`

# 8. ESP32-CAM Integration Design

## 8.1 Transport and Runtime

- Keep ESP32-CAM as HTTP MJPEG producer:
  - stream endpoint: `http://<cam_ip>:81/stream`
  - still endpoint: `http://<cam_ip>/capture`
- Do not send frames through MQTT.
- Use MQTT for:
  - heartbeat/status
  - optional command/ack
  - optional boot/health events

## 8.2 Indoor and Outdoor Roles

- `cam_outdoor`: face detection/recognition evidence for entrance intruder signal.
- `cam_indoor`: face evidence plus flame visual evidence for fire fusion.

## 8.3 Backend Consumption

- `pi/vision_runtime.py` opens both stream URLs.
- Emits semantic events to MQTT topics under `events/<cam_node>`.
- Ingest forwards to Flask endpoint so event storage and fusion remain centralized.

# 9. Security and Local Deployment Design

## 9.1 Broker Authentication

- Enable Mosquitto username/password auth (`password_file`).
- Deny anonymous clients.

## 9.2 Client Identity

- Use per-node credentials and stable client IDs:
  - `mq2_living`, `mq2_door`, `door_force`, `cam_outdoor`, `cam_indoor`
  - `thesis-mqtt-ingest`, `vision-runtime`

## 9.3 Topic Namespace Isolation

- Restrict clients via ACL:
  - each node can publish only to its own `events/<node>` and `status/<node>`
  - camera nodes can access only own `camera/<node>/...` control/ack
  - ingest client can subscribe to `thesis/v1/#`

## 9.4 LAN-Only Assumption

- System is designed for trusted local LAN operation.
- No internet dependency except optional Telegram delivery.

## 9.5 Secrets Handling

- Keep credentials in:
  - firmware-local `secrets.h` (gitignored)
  - `deploy/systemd/thesis.env`
  - `.env` for Flask/vision/ingest runtime
- Do not commit real secrets to repository.

## 9.6 TLS Decision

- TLS is optional, not mandatory for baseline local deployment.
- Recommendation:
  - default no-TLS for isolated home LAN
  - enable TLS only if broker traffic crosses untrusted segments (e.g., shared campus Wi-Fi)

# 10. Methodology for the Revised System

## 10.1 Engineering Method Phases

1. Requirements freeze:
   Preserve event names, fusion semantics, Flask+SQLite stack, Telegram behavior.
2. Transport redesign:
   Replace ESP-NOW/serial path with MQTT broker + ingest service.
3. Firmware migration:
   Convert all nodes/cameras to MQTT publish/status/control architecture.
4. Backend integration:
   Add schema normalization and resilient MQTT->API forwarding.
5. Fusion integrity validation:
   Verify `FIRE`, `INTRUDER`, and `DOOR_FORCE` behavior against preserved intent.
6. Deployment hardening:
   Systemd units, restart policy, env-config, broker ACL.
7. Performance and reliability checks:
   event latency, reconnect behavior, heartbeat/offline detection.

## 10.2 Evaluation Metrics (Aligned to Thesis Objectives)

- Detection correctness:
  - face recognition classification behavior (`AUTHORIZED` vs `UNKNOWN`)
  - flame + smoke fusion correctness
- Alert correctness:
  - `INTRUDER` only when 2-of-3 evidence exists
  - `FIRE` only when smoke + indoor flame align
- Timeliness:
  - event-to-alert latency
- Reliability:
  - node heartbeat continuity
  - MQTT reconnect recovery

# 11. Hardware Requirements

- 1x Raspberry Pi (primary broker/backend host).
- 2x ESP32-C3 + MQ-2 smoke nodes:
  - `mq2_living`
  - `mq2_door`
- 1x ESP32-C3 + door-force sensor assembly (`door_force`).
- 2x ESP32-CAM:
  - `cam_outdoor`
  - `cam_indoor`
- Stable 2.4 GHz Wi-Fi LAN.
- 5V power supplies and proper grounding for each node.
- Optional laptop for fallback vision runtime.

# 12. Software Requirements

- Raspberry Pi OS or equivalent Linux host.
- Python 3.10+ runtime with:
  - Flask
  - OpenCV (`opencv-python`, `opencv-contrib-python` depending on setup)
  - `paho-mqtt`
- Mosquitto broker + mosquitto-clients.
- Arduino IDE or Arduino CLI with:
  - `esp32:esp32` core (installed)
  - `PubSubClient` library
- SQLite3 (bundled with Python runtime).
- systemd for service management.

# 13. Migration Plan from Current Architecture

## Phase A: Transport Cutover

- Stop using `pi/serial_ingest.py` in active deployment.
- Deploy Mosquitto + ACL/passwords on Pi.
- Start `pi/mqtt_ingest.py` as ingest bridge.

## Phase B: Node Firmware Cutover

- Flash MQTT sketches for:
  - smoke node 1, smoke node 2, door-force node, outdoor cam, indoor cam.
- Confirm each node publishes to correct topic path and heartbeat.

## Phase C: Vision Cutover

- Run `pi/vision_runtime.py --event-sink mqtt` with both ESP32-CAM streams.
- Verify semantic event publishing to MQTT.

## Phase D: Fusion/Alert Validation

- Validate:
  - smoke-only: no `FIRE`
  - flame-only: no `FIRE`
  - smoke+flame inside window: `FIRE`
  - one unknown only: no `INTRUDER`
  - two unknowns or unknown+door force: `INTRUDER`
  - door force only: `DOOR_FORCE`

## Phase E: Decommission Legacy Path

- Keep legacy ESP-NOW/serial files in archive directories only.
- Remove legacy services from default systemd stack.

# 14. Repo Rewrite Plan

## Keep (Core Backend)

- `pi/app.py`
- `pi/db.py`
- `pi/fusion.py`
- `pi/notifications.py`
- Vision utilities and trainers:
  - `pi/vision_runtime.py`
  - `pi/vision_utils.py`
  - `pi/fire_utils.py`
  - `pi/train_lbph.py`
  - `pi/train_fire_color.py`

## Modify

- `pi/app.py`: API key enforcement option, camera source mapping, fusion trigger coverage.
- `pi/config.py`: MQTT constants, node metadata, topic helpers.
- `pi/vision_runtime.py`: MQTT publish mode and heartbeat.
- `requirements.txt`: add `paho-mqtt`.
- `README.md` and `docs/*`: MQTT-first instructions.

## Remove from Active Path (Archive Instead)

- `pi/serial_ingest.py` active usage -> archived copy under `pi/archive/serial_ingest.py`.
- ESP-NOW active firmware path -> moved to `firmware/archive/espnow/`.
- Legacy direct HTTP firmware path -> moved to `firmware/archive/legacy_http/`.

## Add

- `pi/mqtt_ingest.py`
- `pi/mqtt_schema.py`
- `deploy/mosquitto/` configs
- systemd templates for mqtt ingest and optional vision
- MQTT firmware set under `firmware/mqtt/`

# 15. Proposed New Folder/File Tree

```text
CpE-Practice-and-Design/
├── deploy/
│   ├── mosquitto/
│   │   ├── mosquitto.conf
│   │   ├── acl
│   │   └── README.md
│   └── systemd/
│       ├── templates/
│       │   ├── thesis-app.service.tmpl
│       │   ├── thesis-mqtt-ingest.service.tmpl
│       │   ├── thesis-vision.service.tmpl
│       │   └── thesis-stack.target.tmpl
│       ├── prepare_units.sh
│       ├── install_units.sh
│       └── thesis.env.example
├── docs/
│   ├── context/
│   ├── instructions/
│   │   ├── transport/mqtt_quick_start.md
│   │   ├── transport/mqtt_deployment.md
│   │   ├── camera/dual_esp32cam.md
│   │   └── deployment/pi_systemd_autostart.md
│   └── archive/...
├── firmware/
│   ├── mqtt/
│   │   ├── common/mqtt_payload.h
│   │   ├── smoke_node1_mqtt/
│   │   ├── smoke_node2_mqtt/
│   │   ├── door_force_mqtt/
│   │   ├── cam_outdoor_mqtt/
│   │   └── cam_indoor_mqtt/
│   └── archive/
│       ├── espnow/
│       └── legacy_http/
├── pi/
│   ├── app.py
│   ├── config.py
│   ├── db.py
│   ├── fusion.py
│   ├── notifications.py
│   ├── mqtt_ingest.py
│   ├── mqtt_schema.py
│   ├── vision_runtime.py
│   └── archive/serial_ingest.py
├── README.md
└── project_description.md
```

# 16. File-by-File Change List

## Added

- `pi/mqtt_ingest.py`: dedicated MQTT consumer/forwarder service.
- `pi/mqtt_schema.py`: compact schema normalization and topic parsing.
- `deploy/mosquitto/mosquitto.conf`
- `deploy/mosquitto/acl`
- `deploy/mosquitto/README.md`
- `deploy/systemd/templates/thesis-mqtt-ingest.service.tmpl`
- `deploy/systemd/templates/thesis-vision.service.tmpl`
- MQTT firmware sketches under `firmware/mqtt/...`

## Modified (Key)

- `pi/app.py`:
  - optional `SENSOR_API_KEY` enforcement,
  - camera node-to-source mapping (`CAM_OUTDOOR`, `CAM_INDOOR`),
  - fusion triggers include `SMOKE_HIGH`, `FLAME_SIGNAL`, `UNKNOWN`, `DOOR_FORCE`.
- `pi/config.py`:
  - MQTT host/port/user/password/topic constants,
  - node metadata and aliases,
  - topic helper functions.
- `pi/vision_runtime.py`:
  - sink modes (`mqtt`, `api`, `db`),
  - MQTT event/status publishing behavior.
- `requirements.txt`: added `paho-mqtt`.
- systemd prep/install scripts updated for MQTT stack.
- project docs and bootstrap references updated for MQTT-first path.

## Archived

- `pi/archive/serial_ingest.py`
- `firmware/archive/espnow/...`
- `firmware/archive/legacy_http/...`

# 17. Deployment and Runtime Plan

## 17.1 Raspberry Pi Primary Runtime

1. Install dependencies (`pip install -r requirements.txt`, Mosquitto packages).
2. Configure broker auth (`deploy/mosquitto/*`).
3. Render and install systemd units:
   - `deploy/systemd/prepare_units.sh`
   - `deploy/systemd/install_units.sh`
4. Enable stack target:
   - `thesis-app.service`
   - `thesis-mqtt-ingest.service`
   - optional `thesis-vision.service`

## 17.2 Startup Order

1. `mosquitto.service`
2. `thesis-app.service`
3. `thesis-mqtt-ingest.service`
4. optional `thesis-vision.service`

## 17.3 Runtime Health Checks

- MQTT ingest logs show connected/subscribed and increasing `ok` forwards.
- Dashboard node status reflects periodic heartbeats.
- `/events` route shows smoke/door/vision events from MQTT path.

# 18. Laptop Fallback Strategy

- Keep laptop fallback supported for vision only.
- Default design keeps Raspberry Pi as primary host for broker/backend/UI/DB/alerts.
- Fallback mode:
  - run `pi/vision_runtime.py --event-sink mqtt` on laptop,
  - point MQTT host to Pi broker,
  - keep Flask + ingest + SQLite on Pi.
- Benefit:
  - heavy inference can be offloaded without changing backend architecture or breaking fusion semantics.

# 19. Risks, Tradeoffs, and Justifications

- Risk: `PubSubClient` library not installed in Arduino environment blocks firmware compile.
  - Mitigation: install `PubSubClient` once per dev machine; sketches now tolerate missing `secrets.h` by falling back to `secrets.example.h`.
- Tradeoff: no TLS by default on LAN.
  - Justification: lower operational complexity for thesis deployment; TLS retained as optional hardening path.
- Tradeoff: Flask still receives events through HTTP from ingest.
  - Justification: minimizes backend rewrite, preserves current API contract and dashboard integration.
- Algorithm decision:
  - Primary path keeps LBPH face recognition + current lightweight flame-color/ratio pipeline for Raspberry Pi feasibility and reproducibility.
  - Optional upgrade path (laptop fallback only) can use stronger face embedding models, but must still emit the same event names (`UNKNOWN`, `AUTHORIZED`, `FLAME_SIGNAL`) to preserve backend/fusion contracts.
- Risk: Raspberry Pi 2 may be tight for continuous dual-stream vision.
  - Mitigation: keep laptop fallback for vision while retaining Pi as system authority.
- Tradeoff: MQTT payloads are compact and less self-descriptive.
  - Justification: reduced bandwidth and parsing overhead on constrained nodes while preserving schema versioning (`v`) and notes (`m`).
