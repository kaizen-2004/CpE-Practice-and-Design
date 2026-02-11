# Condo Monitoring System (Local-First)

Local-first condo monitoring system for:
- Intruder detection (face recognition using LBPH)
- Fire detection (smoke + flame fusion)
- Alerts, snapshots, history, health, and daily summary

Scope: **Living Room** and **Door Entrance Area** only (demo-ready setup).

## 1) Setup

```bash
python -m venv .venv
# activate venv
pip install -r requirements.txt
python pi/init_db.py
```

## 2) Run Web App

```bash
python pi/app.py
```

Open: `http://127.0.0.1:5000`

Main page: `/dashboard`

## 3) Vision Runtime (Cameras)

Laptop webcam:
```bash
python pi/vision_runtime.py --camera-mode webcam
```

Two local webcams:
```bash
python pi/vision_runtime.py --camera-mode webcam --outdoor-url 0 --indoor-url 1
```

Two ESP32-CAM streams:
```bash
python pi/vision_runtime.py --camera-mode esp32 \
  --outdoor-url http://OUTDOOR_IP:81/stream \
  --indoor-url http://INDOOR_IP:81/stream
```

Indoor camera is mapped to **Living Room** (flame detection + indoor face events).  
Outdoor camera is mapped to **Door Entrance Area** (face events).

## 4) Sensor Ingestion (ESP32-C3)

Endpoint: `POST /api/sensors/event`

Minimal payload:
```json
{ "node": "mq2_living", "event": "SMOKE_HIGH" }
```

Example with value:
```json
{
  "node": "door_force",
  "event": "DOOR_FORCE",
  "value": 0.74,
  "unit": "g"
}
```

Supported node IDs:
- `mq2_living`
- `mq2_door`
- `door_force`
- `cam_indoor`
- `cam_outdoor`

## 5) Face Training

Go to `/training`:
1. Enter person name
2. Capture samples using either:
   - Browser camera (`Start` + `Capture` / `Auto Capture`)
   - External source (`Capture from External Source`, e.g. `0` or stream URL)
3. Reach at least minimum samples (`FACE_MIN_SAMPLES`, default `16`)
4. Prefer target samples (`FACE_TARGET_SAMPLES`, default `24`)
5. Click **Train Face Model (LBPH)**

The runtime auto-reloads LBPH model changes.

## 6) Fire Training

Go to `/training`:
1. Upload labeled images to `flame` and `non_flame`
2. Click **Train Fire Model**

This writes: `models/fire_color.json`

## 7) Environment Variables

- `CAMERA_MODE=webcam|esp32|auto`
- `OUTDOOR_URL` / `INDOOR_URL`
- `FACE_MIN_SAMPLES` (default `16`)
- `FACE_TARGET_SAMPLES` (default `24`)
- `UNKNOWN_THRESHOLD`, `UNKNOWN_STREAK`, `ALERT_COOLDOWN`
- `FLAME_STREAK`, `FIRE_COOLDOWN`, `FIRE_RATIO_THRESHOLD`
- `FIRE_FUSION_WINDOW`, `INTRUDER_FUSION_WINDOW`
- `NODE_OFFLINE_SECONDS`

## 8) Notes

- Fire alerts require **both** flame + smoke within the fusion window.
- Intruder alerts require **two-of-three** evidence within the fusion window:
  - Outdoor unknown face
  - Indoor unknown face
  - Door-force event
