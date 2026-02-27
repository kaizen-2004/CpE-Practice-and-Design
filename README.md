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

### Recommended: Run With `.env` (so settings survive IDE restart)

Create `.env` once (already ignored by git):

```bash
cat > .env <<'EOF'
OUTDOOR_CAM_SOURCE=/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera-video-index0
INDOOR_CAM_SOURCE=/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera-video-index0
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=-1003849318611
PUBLIC_BASE_URL=https://YOUR-TAILSCALE-HOST
LOCAL_STREAM_FPS=15
LOCAL_CAM_JPEG_QUALITY=65
EOF
```

Load env + run app:

```bash
set -a; source .env; set +a
python pi/app.py
```

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

Real-time face pipeline inside the system:
- Capture frame
- Detect face(s)
- Preprocess face ROI
- Predict with LBPH
- Apply unknown threshold
- Display bounding boxes + labels on camera view
- Trigger face-related events/alerts

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
3. For each capture: detect face -> preprocess (200x200 grayscale) -> label by person name -> save sample
4. Reach at least minimum samples (`FACE_MIN_SAMPLES`, default `16`)
5. Prefer target samples (`FACE_TARGET_SAMPLES`, default `24`)
6. Click **Train Face Model (LBPH)** (model + labels are saved in `models/`)

The runtime auto-reloads LBPH model changes.

## 6) Fire Training

Go to `/training`:
1. Upload labeled images to `flame` and `non_flame`
2. Click **Train Fire Model**

This writes: `models/fire_color.json`

## 7) Environment Variables

- `CAMERA_MODE=webcam|esp32|auto`
- `OUTDOOR_URL` / `INDOOR_URL`
- `OUTDOOR_CAM_SOURCE` / `INDOOR_CAM_SOURCE` (local USB source, e.g. `0`, `1`, `/dev/v4l/by-id/...`)
- `LOCAL_CAM_JPEG_QUALITY` (default `80`, lower = smaller/faster preview frame)
- `CAMERA_REFRESH_MS` (dashboard preview refresh interval, default `900`)
- `LOCAL_CAM_RETRY_SECONDS` (default `2.0`, retry delay when local camera is missing)
- `LOCAL_STREAM_FPS` (default `12`, live stream FPS cap for local USB preview)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (for alert notifications)
- `PUBLIC_BASE_URL` (public/Tailscale URL used in notification links, e.g. `https://<tailnet-host>`)
- `ALERT_REMINDER_SCHEDULE` (default `0,60,180,300`, seconds from alert start)
- `ALERT_REMINDER_REPEAT_SECONDS` (default `600`, repeat reminder interval while still ACTIVE)
- `ALERT_NOTIFIER_POLL_SECONDS` (default `5`, notifier loop interval)
- `ALERT_NOTIFY_FAIL_RETRY_SECONDS` (default `60`, retry delay after failed send)
- `TELEGRAM_SEND_TIMEOUT` (default `8`)
- `FACE_MIN_SAMPLES` (default `16`)
- `FACE_TARGET_SAMPLES` (default `24`)
- `UNKNOWN_THRESHOLD`, `UNKNOWN_STREAK`, `ALERT_COOLDOWN`
- `FLAME_STREAK`, `FIRE_COOLDOWN`, `FIRE_RATIO_THRESHOLD`
- `FIRE_MIN_BLOB_RATIO` (default `0.0015`, minimum largest connected flame area ratio)
- `FIRE_MIN_HOT_RATIO` (default `0.0008`, minimum bright warm-core pixel ratio)
- `FIRE_FUSION_WINDOW`, `INTRUDER_FUSION_WINDOW`
- `NODE_OFFLINE_SECONDS`

If `OUTDOOR_CAM_SOURCE` / `INDOOR_CAM_SOURCE` is set, dashboard camera preview uses local USB capture through Flask endpoints:
- `/camera/local/frame/outdoor`
- `/camera/local/frame/indoor`
- `/camera/local/stream/outdoor`
- `/camera/local/stream/indoor`

Tip: set a slot to `none` (or unset it) to disable that camera block without retries.

## 8) Notes

- Fire alerts require **both** flame + smoke within the fusion window.
- Intruder alerts require **two-of-three** evidence within the fusion window:
  - Outdoor unknown face
  - Indoor unknown face
  - Door-force event

## 9) Persistent Telegram Alerts

1. Create a Telegram bot with `@BotFather` and copy bot token.
2. Start chat with your bot once.
3. Add bot to your family group and send at least one message.
4. Get your group chat ID using:

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"
```

Use `message.chat.id` where `chat.type` is `group` or `supergroup` (usually starts with `-100`).
5. Set env vars before running app:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="-100xxxxxxxxxx"
export PUBLIC_BASE_URL="https://your-tailnet-host"
```

When an alert is `ACTIVE`, the app sends:
- initial message
- reminder messages based on `ALERT_REMINDER_SCHEDULE`
- repeat reminders every `ALERT_REMINDER_REPEAT_SECONDS` until ACK/RESOLVED

## 10) Phone Icon Access (No Manual URL Typing)

The dashboard is installable as a web app icon:
- Open dashboard on phone browser.
- Tap **Install App** (Android/Chrome), or use **Share → Add to Home Screen** on iPhone Safari.
- After install, open the system directly from the icon.

## 11) Common Issues

- Camera works before, then fails after IDE restart:
  - cause: camera env vars were not loaded in the new terminal.
  - fix: run `set -a; source .env; set +a` before `python pi/app.py`.

- Telegram shows inactive after restart:
  - cause: Telegram env vars are missing in current shell.
  - fix: load `.env` again and restart app.

- Camera cannot be opened:
  - ensure no other app is using the camera.
  - verify source path with `v4l2-ctl --list-devices`.

- Security note:
  - if bot token is exposed, regenerate it in `@BotFather` immediately.
