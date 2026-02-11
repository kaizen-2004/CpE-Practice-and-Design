import os
import json
import time
import argparse
from datetime import datetime, timezone

import cv2

from db import (
    init_db,
    create_event,
    create_snapshot,
    update_node_seen,
)
from vision_utils import save_frame_snapshot
from fire_utils import load_fire_model, detect_flame_signal
from fusion import handle_fire_signal, handle_intruder_evidence
from config import EVENT_UNKNOWN, EVENT_AUTHORIZED, EVENT_FLAME_SIGNAL

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "lbph.yml")
LABELS_PATH = os.path.join(MODELS_DIR, "labels.json")
FIRE_MODEL_PATH = os.path.join(MODELS_DIR, "fire_color.json")

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

def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")

def _coerce_capture_source(source):
    if _is_empty(source):
        return None
    if isinstance(source, int):
        return source
    s = str(source).strip()
    if s.lower() in ("webcam", "laptop", "camera"):
        return 0
    if s.isdigit():
        return int(s)
    return s

def _resolve_sources(args):
    outdoor = args.outdoor_url
    indoor = args.indoor_url

    if args.camera_mode == "webcam":
        if _is_empty(outdoor):
            outdoor = "0"
    elif args.camera_mode == "esp32":
        if _is_empty(outdoor):
            raise SystemExit(
                "Outdoor stream not set. Provide --outdoor-url or OUTDOOR_URL when using --camera-mode esp32."
            )

    if _is_empty(outdoor):
        outdoor = "0"

    return outdoor, indoor

def main():
    parser = argparse.ArgumentParser(description="OpenCV runtime to generate real events/snapshots/alerts.")
    parser.add_argument("--camera-mode", default=os.environ.get("CAMERA_MODE", "auto"),
                        type=str.lower, choices=["auto", "webcam", "esp32"],
                        help="Camera source preset: auto uses env or defaults, webcam uses local camera, esp32 expects URLs")
    parser.add_argument("--outdoor-url", default=os.environ.get("OUTDOOR_URL"),
                        help="Outdoor stream URL or webcam index (env OUTDOOR_URL). Examples: 0 or http://<ip>:81/stream")
    parser.add_argument("--indoor-url", default=os.environ.get("INDOOR_URL"),
                        help="Indoor stream URL or webcam index (env INDOOR_URL). Optional.")
    parser.add_argument("--process-every", type=int, default=int(os.environ.get("PROCESS_EVERY", "5")),
                        help="Process 1 out of N frames (default 5)")
    parser.add_argument("--unknown-streak", type=int, default=int(os.environ.get("UNKNOWN_STREAK", "12")),
                        help="Consecutive UNKNOWN before INTRUDER alert (default 12)")
    parser.add_argument("--unknown-threshold", type=float, default=float(os.environ.get("UNKNOWN_THRESHOLD", "65")),
                        help="LBPH threshold: if conf > threshold => UNKNOWN (default 65)")
    parser.add_argument("--cooldown-seconds", type=int, default=int(os.environ.get("ALERT_COOLDOWN", "45")),
                        help="Cooldown between INTRUDER alerts (default 45s)")
    parser.add_argument("--flame-streak", type=int, default=int(os.environ.get("FLAME_STREAK", "8")),
                        help="Consecutive indoor flame signals before FIRE fusion check (default 8)")
    parser.add_argument("--fire-cooldown-seconds", type=int, default=int(os.environ.get("FIRE_COOLDOWN", "75")),
                        help="Cooldown between FIRE alerts (default 75s)")
    parser.add_argument("--fire-ratio-threshold", type=float, default=float(os.environ.get("FIRE_RATIO_THRESHOLD", "0")),
                        help="Manual threshold override for flame ratio; 0 uses trained model.")
    args = parser.parse_args()

    init_db()

    outdoor_src, indoor_src = _resolve_sources(args)

    outdoor = cv2.VideoCapture(_coerce_capture_source(outdoor_src))
    if not outdoor.isOpened():
        raise SystemExit(f"❌ Cannot open outdoor stream: {outdoor_src}")

    indoor = None
    if not _is_empty(indoor_src):
        indoor = cv2.VideoCapture(_coerce_capture_source(indoor_src))
        if not indoor.isOpened():
            print(f"⚠️  Cannot open indoor stream: {indoor_src} (continuing with outdoor only)")
            indoor = None

    recognizer, id_to_name = load_lbph()
    model_mtime = os.path.getmtime(MODEL_PATH) if os.path.exists(MODEL_PATH) else 0
    fire_model = load_fire_model(FIRE_MODEL_PATH)
    fire_model_mtime = os.path.getmtime(FIRE_MODEL_PATH) if os.path.exists(FIRE_MODEL_PATH) else 0
    fire_threshold = args.fire_ratio_threshold if args.fire_ratio_threshold > 0 else (
        float(fire_model["ratio_threshold"]) if fire_model else 0.0
    )

    unknown_streak_outdoor = 0
    unknown_streak_indoor = 0
    flame_streak = 0
    frame_i = 0

    print("✅ Vision runtime started")
    print(f"Mode: {args.camera_mode} | Outdoor: {outdoor_src} | Indoor: {indoor_src or '(none)'}")
    if recognizer is None:
        print("ℹ️  No LBPH model loaded (train later). All faces are UNKNOWN until training.")
    if fire_threshold > 0:
        print(f"ℹ️  Fire detection threshold={fire_threshold:.4f}")
    else:
        print("ℹ️  Fire model not loaded. Indoor flame detection is disabled until fire training.")

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
        if os.path.exists(FIRE_MODEL_PATH):
            fm = os.path.getmtime(FIRE_MODEL_PATH)
            if fm != fire_model_mtime:
                fire_model = load_fire_model(FIRE_MODEL_PATH)
                fire_model_mtime = fm
                if args.fire_ratio_threshold > 0:
                    fire_threshold = args.fire_ratio_threshold
                else:
                    fire_threshold = float(fire_model["ratio_threshold"]) if fire_model else 0.0
                print(f"🔄 Reloaded fire model (threshold={fire_threshold:.4f}).")

        update_node_seen("cam_outdoor", note="opencv loop")
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        rects = detect_faces(gray)
        if len(rects) == 0:
            unknown_streak_outdoor = max(0, unknown_streak_outdoor - 1)
        else:
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
                unknown_streak_outdoor += 1
                create_event(EVENT_UNKNOWN, "CAM_OUTDOOR", details=f"conf={conf:.1f}", ts=ts, room="Door Entrance Area")

                if unknown_streak_outdoor in (1, 6, args.unknown_streak):
                    rel, _ = save_frame_snapshot(frame, prefix=f"outdoor_unknown_{unknown_streak_outdoor}", ts_iso=ts)
                    create_snapshot("FACE_UNKNOWN", "UNKNOWN", rel, linked_alert_id=None, note=f"conf={conf:.1f}", ts=ts)

                alert_id = handle_intruder_evidence(ts, cooldown_seconds=args.cooldown_seconds)
                if alert_id:
                    print(f"🚨 INTRUDER alert #{alert_id} created (fusion).")
            else:
                unknown_streak_outdoor = 0
                create_event(EVENT_AUTHORIZED, "CAM_OUTDOOR", details=f"name={label_name} conf={conf:.1f}", ts=ts, room="Door Entrance Area")

        if indoor is not None and (frame_i % (args.process_every * 6) == 0):
            ok2, frame2 = indoor.read()
            if ok2 and frame2 is not None:
                update_node_seen("cam_indoor", note="opencv loop")
                gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
                rects2 = detect_faces(gray2)
                if len(rects2) == 0:
                    unknown_streak_indoor = max(0, unknown_streak_indoor - 1)
                else:
                    rect2 = max(rects2, key=lambda r: r[2]*r[3])
                    roi2 = prep_roi(gray2, rect2)
                    label2 = "UNKNOWN"
                    conf2 = 999.0
                    if recognizer is not None:
                        try:
                            pred_id2, conf2 = recognizer.predict(roi2)
                            label2 = id_to_name.get(pred_id2, "UNKNOWN")
                            if conf2 > args.unknown_threshold:
                                label2 = "UNKNOWN"
                        except Exception:
                            label2 = "UNKNOWN"

                    if label2 == "UNKNOWN":
                        unknown_streak_indoor += 1
                        create_event(EVENT_UNKNOWN, "CAM_INDOOR", details=f"conf={conf2:.1f}", ts=ts, room="Living Room")
                        if unknown_streak_indoor in (1, 4, args.unknown_streak):
                            rel2, _ = save_frame_snapshot(frame2, prefix=f"indoor_unknown_{unknown_streak_indoor}", ts_iso=ts)
                            create_snapshot("FACE_UNKNOWN", "UNKNOWN", rel2, linked_alert_id=None, note=f"conf={conf2:.1f}", ts=ts)
                        alert_id = handle_intruder_evidence(ts, cooldown_seconds=args.cooldown_seconds)
                        if alert_id:
                            print(f"🚨 INTRUDER alert #{alert_id} created (fusion).")
                    else:
                        unknown_streak_indoor = 0
                        create_event(EVENT_AUTHORIZED, "CAM_INDOOR", details=f"name={label2} conf={conf2:.1f}", ts=ts, room="Living Room")

                if fire_threshold > 0:
                    is_flame, ratio = detect_flame_signal(frame2, fire_threshold)
                    if is_flame:
                        flame_streak += 1
                        create_event(EVENT_FLAME_SIGNAL, "CAM_INDOOR", details=f"ratio={ratio:.4f}", ts=ts, room="Living Room")
                        if flame_streak in (1, args.flame_streak):
                            rel, _ = save_frame_snapshot(frame2, prefix=f"indoor_flame_{flame_streak}", ts_iso=ts)
                            create_snapshot("FLAME_SIGNAL", "FLAME", rel, linked_alert_id=None, note=f"ratio={ratio:.4f}", ts=ts)

                        alert_id = handle_fire_signal(ts, cooldown_seconds=args.fire_cooldown_seconds)
                        if alert_id:
                            flame_streak = 0
                            print(f"🔥 FIRE alert #{alert_id} created (fusion).")
                    else:
                        flame_streak = max(0, flame_streak - 1)

        time.sleep(0.01)

if __name__ == "__main__":
    main()
