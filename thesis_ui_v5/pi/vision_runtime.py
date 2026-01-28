import os
import json
import time
import argparse
from datetime import datetime, timezone

import cv2

from db import (
    init_db,
    create_event,
    create_alert,
    create_snapshot,
    attach_snapshot_to_alert,
    update_node_seen,
    get_guest_mode,
)
from vision_utils import save_frame_snapshot

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "lbph.yml")
LABELS_PATH = os.path.join(MODELS_DIR, "labels.json")

def load_lbph():
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except Exception:
        return None, {}
    if not (os.path.exists(MODEL_PATH) and os.path.exists(LABELS_PATH)):
        return None, {}
    try:
        recognizer.read(MODEL_PATH)
        with open(LABELS_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        id_to_name = {int(k): v for k, v in meta.get("id_to_name", {}).items()}
        return recognizer, id_to_name
    except Exception:
        return None, {}

def detect_faces(gray):
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))

def prep_roi(gray, rect):
    x, y, w, h = rect
    roi = gray[y:y+h, x:x+w]
    roi = cv2.resize(roi, (200, 200), interpolation=cv2.INTER_AREA)
    return roi

def main():
    parser = argparse.ArgumentParser(description="Week 6-7: OpenCV runtime to generate real events/snapshots/alerts.")
    parser.add_argument("--outdoor-url", default=os.environ.get("OUTDOOR_URL", "0"),
                        help="Outdoor stream URL or webcam index (default env OUTDOOR_URL or 0)")
    parser.add_argument("--indoor-url", default=os.environ.get("INDOOR_URL", ""), help="Indoor stream URL (optional)")
    parser.add_argument("--process-every", type=int, default=int(os.environ.get("PROCESS_EVERY", "5")),
                        help="Process 1 out of N frames (default 5)")
    parser.add_argument("--unknown-streak", type=int, default=int(os.environ.get("UNKNOWN_STREAK", "12")),
                        help="Consecutive UNKNOWN before INTRUDER alert (default 12)")
    parser.add_argument("--unknown-threshold", type=float, default=float(os.environ.get("UNKNOWN_THRESHOLD", "65")),
                        help="LBPH threshold: if conf > threshold => UNKNOWN (default 65)")
    parser.add_argument("--cooldown-seconds", type=int, default=int(os.environ.get("ALERT_COOLDOWN", "45")),
                        help="Cooldown between INTRUDER alerts (default 45s)")
    args = parser.parse_args()

    init_db()

    outdoor = cv2.VideoCapture(args.outdoor_url if not args.outdoor_url.isdigit() else int(args.outdoor_url))
    if not outdoor.isOpened():
        raise SystemExit(f"❌ Cannot open outdoor stream: {args.outdoor_url}")

    indoor = None
    if args.indoor_url:
        indoor = cv2.VideoCapture(args.indoor_url)
        if not indoor.isOpened():
            print(f"⚠️  Cannot open indoor stream: {args.indoor_url} (continuing with outdoor only)")
            indoor = None

    recognizer, id_to_name = load_lbph()
    model_mtime = os.path.getmtime(MODEL_PATH) if os.path.exists(MODEL_PATH) else 0

    unknown_streak = 0
    last_alert_ts = 0.0
    frame_i = 0

    print("✅ Vision runtime started")
    print(f"Outdoor: {args.outdoor_url} | Indoor: {args.indoor_url or '(none)'}")
    if recognizer is None:
        print("ℹ️  No LBPH model loaded (train later). All faces are UNKNOWN until training.")

    while True:
        ok, frame = outdoor.read()
        if not ok or frame is None:
            time.sleep(0.2)
            continue

        frame_i += 1
        if frame_i % args.process_every != 0:
            continue

        # Reload model if updated
        if os.path.exists(MODEL_PATH):
            m = os.path.getmtime(MODEL_PATH)
            if m != model_mtime:
                recognizer, id_to_name = load_lbph()
                model_mtime = m
                print("🔄 Reloaded LBPH model after retrain.")

        update_node_seen("cam_outdoor", note="opencv loop")
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        rects = detect_faces(gray)
        if len(rects) == 0:
            unknown_streak = max(0, unknown_streak - 1)
            time.sleep(0.01)
            continue

        rect = max(rects, key=lambda r: r[2]*r[3])
        roi = prep_roi(gray, rect)

        label_name = "UNKNOWN"
        conf = 999.0
        if recognizer is not None:
            try:
                pred_id, conf = recognizer.predict(roi)
                label_name = id_to_name.get(pred_id, "UNKNOWN")
                if conf > args.unknown_threshold:
                    label_name = "UNKNOWN"
            except Exception:
                label_name = "UNKNOWN"

        if label_name == "UNKNOWN":
            unknown_streak += 1
            create_event("UNKNOWN", "CAM_OUTDOOR", details=f"conf={conf:.1f}", ts=ts)

            if unknown_streak in (1, 6, args.unknown_streak):
                rel, _ = save_frame_snapshot(frame, prefix=f"outdoor_unknown_{unknown_streak}", ts_iso=ts)
                create_snapshot("FACE_UNKNOWN", "UNKNOWN", rel, linked_alert_id=None, note=f"conf={conf:.1f}", ts=ts)

            now = time.time()
            if not get_guest_mode() and unknown_streak >= args.unknown_streak and (now - last_alert_ts) > args.cooldown_seconds:
                rel, _ = save_frame_snapshot(frame, prefix="outdoor_intruder", ts_iso=ts)
                alert_id = create_alert(
                    "INTRUDER",
                    room="Door",
                    severity=3,
                    status="ACTIVE",
                    details=f"Repeated UNKNOWN (streak={unknown_streak}, conf={conf:.1f})",
                    snapshot_path=f"snapshots/{rel}",
                    ts=ts,
                )
                create_snapshot("FACE_UNKNOWN", "UNKNOWN", rel, linked_alert_id=alert_id, note="alert snapshot", ts=ts)
                attach_snapshot_to_alert(alert_id, rel)
                last_alert_ts = now
                print(f"🚨 INTRUDER alert #{alert_id} created (streak={unknown_streak}).")
                unknown_streak = 0
        else:
            unknown_streak = 0
            create_event("AUTHORIZED", "CAM_OUTDOOR", details=f"name={label_name} conf={conf:.1f}", ts=ts)

        if indoor is not None and (frame_i % (args.process_every * 6) == 0):
            ok2, frame2 = indoor.read()
            if ok2 and frame2 is not None:
                update_node_seen("cam_indoor", note="opencv loop")
                # Flame detection hook will go here in Week 8.

        time.sleep(0.01)

if __name__ == "__main__":
    main()
