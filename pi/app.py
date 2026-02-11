from flask import Flask, redirect, render_template, request, url_for, flash, send_from_directory, abort, Response, jsonify
import csv
import io
import json
import base64
import re
from datetime import datetime, timezone, timedelta
import os
import sys
import subprocess

import cv2
import numpy as np

from db import (
    init_db,
    # alerts
    list_active_alerts,
    list_history_alerts,
    list_recent_events,
    ack_alert,
    get_guest_mode,
    set_guest_mode,
    distinct_alert_types,
    distinct_alert_rooms,
    count_active_alerts,
    get_alert,
    events_near_ts,
    # health
    list_node_status,
    update_node_seen,
    # snapshots
    list_snapshots,
    get_snapshot,
    list_snapshots_for_alert,
    distinct_snapshot_types,
    distinct_snapshot_labels,
    update_snapshot_label,
    SNAPSHOT_DIR,
    # faces
    list_faces,
    get_face,
    create_face,
    delete_face,
    add_face_sample,
    list_face_samples,
    # summary
    summary_for_date,
    # events
    create_event,
    get_latest_event,
)
from vision_utils import export_face_sample_from_snapshot, extract_face_roi
from config import (
    ROOMS,
    NODE_META,
    NODE_OFFLINE_SECONDS,
    normalize_node_id,
    get_node_meta,
    EVENT_SMOKE_HIGH,
    EVENT_DOOR_FORCE,
    EVENT_FLAME_SIGNAL,
    EVENT_UNKNOWN,
)
from fusion import handle_fire_signal, handle_intruder_evidence

app = Flask(__name__)
app.secret_key = "dev-only-change-me"  # change later for real deployments

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "faces")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
FIRE_DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "fire")
FIRE_FLAME_DIR = os.path.join(FIRE_DATASET_DIR, "flame")
FIRE_NON_FLAME_DIR = os.path.join(FIRE_DATASET_DIR, "non_flame")
FIRE_MODEL_PATH = os.path.join(MODELS_DIR, "fire_color.json")
FACE_TARGET_SAMPLES = int(os.environ.get("FACE_TARGET_SAMPLES", "24"))
FACE_MIN_SAMPLES = int(os.environ.get("FACE_MIN_SAMPLES", "16"))


init_db()

def _parse_iso(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None

def _is_online(last_seen_ts: str) -> bool:
    if not last_seen_ts:
        return False
    dt = _parse_iso(last_seen_ts)
    if not dt:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() <= NODE_OFFLINE_SECONDS


def _ensure_training_dirs() -> None:
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(FIRE_FLAME_DIR, exist_ok=True)
    os.makedirs(FIRE_NON_FLAME_DIR, exist_ok=True)


def _safe_name(raw: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 _-]+", "", (raw or "").strip())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _count_images(dir_path: str) -> int:
    if not os.path.isdir(dir_path):
        return 0
    count = 0
    for name in os.listdir(dir_path):
        if name.lower().endswith((".png", ".jpg", ".jpeg")):
            count += 1
    return count


def _face_count_for_name(name: str) -> int:
    return _count_images(os.path.join(DATASET_DIR, name))


def _ensure_face_record(name: str) -> int:
    target = name.lower()
    for face in list_faces():
        if str(face["name"]).strip().lower() == target:
            return int(face["id"])
    return create_face(name=name, is_authorized=True, note="created from training page")


def _decode_data_url_image(data_url: str):
    if not data_url or "," not in data_url:
        return None
    try:
        _, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _coerce_capture_source(raw_source: str):
    s = str(raw_source or "").strip()
    if s == "":
        return 0
    if s.isdigit():
        return int(s)
    return s


def _validate_face_roi(face_roi):
    if face_roi is None:
        return "No face detected. Keep face centered and retry."
    sharpness = float(cv2.Laplacian(face_roi, cv2.CV_64F).var())
    brightness = float(face_roi.mean())
    if sharpness < 45.0:
        return "Frame is blurry. Hold still and retry."
    if brightness < 30.0 or brightness > 230.0:
        return "Lighting is poor. Use moderate lighting."
    return None


def _save_face_sample(name: str, face_roi):
    person_dir = os.path.join(DATASET_DIR, name)
    os.makedirs(person_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    out_path = os.path.join(person_dir, f"{ts}.png")
    cv2.imwrite(out_path, face_roi)
    _ensure_face_record(name)
    count = _face_count_for_name(name)
    return {
        "ok": True,
        "name": name,
        "count": count,
        "min_required": FACE_MIN_SAMPLES,
        "target": FACE_TARGET_SAMPLES,
        "remaining": max(0, FACE_TARGET_SAMPLES - count),
        "ready": count >= FACE_MIN_SAMPLES,
        "target_reached": count >= FACE_TARGET_SAMPLES,
    }


def _collect_face_dataset_rows():
    rows = []
    if os.path.isdir(DATASET_DIR):
        for person in sorted(os.listdir(DATASET_DIR)):
            full = os.path.join(DATASET_DIR, person)
            if not os.path.isdir(full):
                continue
            count = _count_images(full)
            rows.append(
                {
                    "name": person,
                    "count": count,
                    "ready": count >= FACE_MIN_SAMPLES,
                    "target_reached": count >= FACE_TARGET_SAMPLES,
                }
            )
    return rows


def _read_fire_model_meta():
    if not os.path.exists(FIRE_MODEL_PATH):
        return None
    try:
        with open(FIRE_MODEL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _run_face_training():
    _ensure_training_dirs()
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "pi", "train_lbph.py")]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    msg = (res.stdout + "\n" + res.stderr).strip()
    return res.returncode == 0, msg


def _run_fire_training():
    _ensure_training_dirs()
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "pi", "train_fire_color.py")]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    msg = (res.stdout + "\n" + res.stderr).strip()
    return res.returncode == 0, msg

@app.context_processor
def inject_globals():
    return {
        "guest_mode": get_guest_mode(),
        "active_alert_count": count_active_alerts(),
    }

@app.get("/")
def home():
    return redirect(url_for("dashboard"))

# ---- Dashboard / Alerts ----
@app.get("/dashboard")
def dashboard():
    alerts = list_active_alerts(limit=12)
    recent_events = list_recent_events(limit=10)
    node_rows = list_node_status()
    node_map = {n["node"]: n for n in node_rows}

    nodes = []
    for node_id, meta in NODE_META.items():
        row = node_map.get(node_id)
        last_seen = row["last_seen_ts"] if row else ""
        nodes.append(
            {
                "node": node_id,
                "label": meta.get("label", node_id),
                "room": meta.get("room", ""),
                "kind": meta.get("kind", ""),
                "role": meta.get("role", ""),
                "last_seen_ts": last_seen,
                "note": row["note"] if row else "",
                "online": _is_online(last_seen),
            }
        )

    sensors_total = len([n for n in nodes if n["kind"] == "sensor"])
    cameras_total = len([n for n in nodes if n["kind"] == "camera"])
    sensors_online = len([n for n in nodes if n["kind"] == "sensor" and n["online"]])
    cameras_online = len([n for n in nodes if n["kind"] == "camera" and n["online"]])

    def _event_summary(row):
        if not row:
            return None
        return {
            "ts": row["ts"],
            "type": row["type"],
            "source": row["source"],
            "room": row["room"],
            "details": row["details"],
        }

    room_cards = []
    for room in ROOMS:
        room_sensors = [n for n in nodes if n["room"] == room and n["kind"] == "sensor"]
        room_cameras = [n for n in nodes if n["room"] == room and n["kind"] == "camera"]
        if room == "Door Entrance Area":
            latest_unknown = get_latest_event(EVENT_UNKNOWN, source="CAM_OUTDOOR")
        else:
            latest_unknown = get_latest_event(EVENT_UNKNOWN, source="CAM_INDOOR")

        room_cards.append(
            {
                "room": room,
                "sensors": room_sensors,
                "cameras": room_cameras,
                "latest_smoke": _event_summary(get_latest_event(EVENT_SMOKE_HIGH, room=room)),
                "latest_flame": _event_summary(get_latest_event(EVENT_FLAME_SIGNAL, room=room)),
                "latest_door_force": _event_summary(get_latest_event(EVENT_DOOR_FORCE, room=room)),
                "latest_unknown": _event_summary(latest_unknown),
            }
        )
    outdoor_url = os.environ.get("OUTDOOR_URL", "").strip()
    indoor_url = os.environ.get("INDOOR_URL", "").strip()
    return render_template(
        "dashboard.html",
        alerts=alerts,
        recent_events=recent_events,
        nodes=nodes,
        sensors_total=sensors_total,
        cameras_total=cameras_total,
        sensors_online=sensors_online,
        cameras_online=cameras_online,
        room_cards=room_cards,
        outdoor_url=outdoor_url,
        indoor_url=indoor_url,
    )

@app.get("/alert/<int:alert_id>")
def alert_details(alert_id: int):
    alert = get_alert(alert_id)
    if not alert:
        abort(404)
    snaps = list_snapshots_for_alert(alert_id)
    near_events, start, end = events_near_ts(alert["ts"], window_seconds=600)
    return render_template("alert_details.html", alert=alert, snapshots=snaps, near_events=near_events, win_start=start, win_end=end)

@app.post("/ack/<int:alert_id>")
def ack(alert_id: int):
    status = request.form.get("status", "ACK").upper().strip()
    if status not in ("ACK", "RESOLVED"):
        status = "ACK"

    ok = ack_alert(alert_id, status=status)
    if ok:
        flash(f"Alert #{alert_id} set to {status}.", "success")
    else:
        flash(f"Alert #{alert_id} was not ACTIVE (nothing changed).", "warning")
    return redirect(request.referrer or url_for("dashboard"))

@app.get("/history")
def history():
    type_filter = request.args.get("type", "").strip()
    room_filter = request.args.get("room", "").strip()
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "newest").strip()

    alerts = list_history_alerts(type_filter=type_filter, room_filter=room_filter, q=q, sort=sort)
    types = distinct_alert_types()
    rooms = distinct_alert_rooms()
    return render_template("history.html", alerts=alerts, types=types, rooms=rooms,
                           type_filter=type_filter, room_filter=room_filter, q=q, sort=sort)

# ---- Events ----
@app.get("/events")
def events():
    type_filter = request.args.get("type", "").strip()
    source_filter = request.args.get("source", "").strip()
    room_filter = request.args.get("room", "").strip()
    q = request.args.get("q", "").strip()
    rows = list_recent_events(type_filter=type_filter, source_filter=source_filter, q=q, room_filter=room_filter)
    return render_template("events.html", events=rows, type_filter=type_filter, source_filter=source_filter, room_filter=room_filter, q=q)

# ---- Sensor Ingestion ----
@app.post("/api/sensors/event")
def sensors_event():
    payload = request.get_json(silent=True) or {}
    raw_node = str(payload.get("node", "")).strip()
    event = str(payload.get("event", "")).strip().upper()
    if not raw_node or not event:
        return jsonify({"ok": False, "error": "node and event are required"}), 400

    node_id = normalize_node_id(raw_node)
    if not node_id:
        return jsonify({"ok": False, "error": "invalid node id"}), 400
    meta = get_node_meta(node_id)
    room = str(payload.get("room") or meta.get("room", "")).strip()
    value = payload.get("value")
    unit = str(payload.get("unit") or "").strip()
    ts = str(payload.get("ts") or "").strip() or None
    note = str(payload.get("note") or "").strip()

    details_bits = []
    if value is not None and value != "":
        details_bits.append(f"value={value}{unit}")
    if note:
        details_bits.append(note)
    details = " | ".join(details_bits)

    ts_iso = ts or datetime.now(timezone.utc).isoformat(timespec="seconds")
    create_event(event, source=node_id, details=details, ts=ts_iso, room=room)
    update_node_seen(node_id, note=details or event, ts=ts_iso)
    alert_id = None
    if event == EVENT_SMOKE_HIGH:
        alert_id = handle_fire_signal(ts_iso, room=room)
    elif event == EVENT_DOOR_FORCE:
        alert_id = handle_intruder_evidence(ts_iso, room=room)

    return jsonify({"ok": True, "node": node_id, "event": event, "room": room, "alert_id": alert_id})

# ---- Snapshots ----
@app.get("/snapshots")
def snapshots():
    type_filter = request.args.get("type", "").strip()
    label_filter = request.args.get("label", "").strip()
    q = request.args.get("q", "").strip()

    snaps = list_snapshots(type_filter=type_filter, label_filter=label_filter, q=q)
    types = distinct_snapshot_types()
    labels = distinct_snapshot_labels()
    return render_template("snapshots.html", snapshots=snaps, types=types, labels=labels,
                           type_filter=type_filter, label_filter=label_filter, q=q)

@app.get("/snapshot/<int:snapshot_id>")
def snapshot_details(snapshot_id: int):
    snap = get_snapshot(snapshot_id)
    if not snap:
        abort(404)
    faces = list_faces()
    return render_template("snapshot_details.html", snap=snap, faces=faces)

@app.post("/snapshot/<int:snapshot_id>/label")
def snapshot_set_label(snapshot_id: int):
    label = request.form.get("label", "").strip()
    note = request.form.get("note", "").strip()
    if not label:
        flash("Please choose a label.", "warning")
        return redirect(url_for("snapshot_details", snapshot_id=snapshot_id))
    ok = update_snapshot_label(snapshot_id, label=label, note=note)
    if ok:
        flash(f"Snapshot #{snapshot_id} labeled as {label}.", "success")
    else:
        flash("Snapshot not found.", "warning")
    return redirect(url_for("snapshot_details", snapshot_id=snapshot_id))

@app.post("/faces/from_snapshot/<int:snapshot_id>")
def create_face_from_snapshot(snapshot_id: int):
    name = request.form.get("name", "").strip()
    note = request.form.get("note", "").strip()
    if not name:
        flash("Face name is required.", "warning")
        return redirect(url_for("snapshot_details", snapshot_id=snapshot_id))

    face_id = create_face(name=name, is_authorized=True, note=note)
    add_face_sample(face_id, snapshot_id, note="added from snapshot")

    # Export a cropped face ROI sample into the LBPH dataset folder
    try:
        os.makedirs(DATASET_DIR, exist_ok=True)
        person_dir = os.path.join(DATASET_DIR, name.strip())
        from db import get_snapshot, SNAPSHOT_DIR
        snap = get_snapshot(snapshot_id)
        if snap:
            snap_abs = os.path.join(SNAPSHOT_DIR, snap["file_relpath"])
            out_name = f"{snapshot_id}_{snap['ts'].replace(':','-')}.png"
            out_path = export_face_sample_from_snapshot(snap_abs, person_dir, out_name)
            if out_path is None:
                flash("⚠️ Face ROI not found in snapshot (saved face record, but dataset sample not created).", "warning")
    except Exception:
        flash("⚠️ Could not export dataset sample (you can still add samples later).", "warning")


    # Optional convenience: also label the snapshot as AUTHORIZED
    update_snapshot_label(snapshot_id, label="AUTHORIZED")

    flash(f"Created face '{name}' and linked Snapshot #{snapshot_id}.", "success")
    return redirect(url_for("face_details", face_id=face_id))

@app.post("/faces/<int:face_id>/add_sample")
def add_sample_to_face(face_id: int):
    snapshot_id = request.form.get("snapshot_id", "").strip()
    if not snapshot_id.isdigit():
        flash("Invalid snapshot id.", "warning")
        return redirect(url_for("face_details", face_id=face_id))
    ok = add_face_sample(face_id, int(snapshot_id), note="added via UI")

    # Also export ROI sample into dataset folder under this face name
    try:
        face = get_face(face_id)
        from db import get_snapshot, SNAPSHOT_DIR
        snap = get_snapshot(int(snapshot_id))
        if face and snap:
            person_dir = os.path.join(DATASET_DIR, face["name"].strip())
            snap_abs = os.path.join(SNAPSHOT_DIR, snap["file_relpath"])
            out_name = f"{snapshot_id}_{snap['ts'].replace(':','-')}.png"
            export_face_sample_from_snapshot(snap_abs, person_dir, out_name)
    except Exception:
        pass

    if ok:
        flash(f"Added Snapshot #{snapshot_id} as a sample.", "success")
    else:
        flash("That snapshot was already linked or does not exist.", "warning")
    return redirect(url_for("face_details", face_id=face_id))

@app.get("/files/snapshots/<path:filename>")
def serve_snapshot(filename: str):
    return send_from_directory(SNAPSHOT_DIR, filename, as_attachment=False)

# ---- Faces ----
@app.get("/faces")
def faces():
    rows = list_faces()
    return render_template("faces.html", faces=rows)

@app.get("/faces/<int:face_id>")
def face_details(face_id: int):
    face = get_face(face_id)
    if not face:
        abort(404)
    samples = list_face_samples(face_id)
    return render_template("face_details.html", face=face, samples=samples)

@app.post("/faces/new")
def faces_new():
    name = request.form.get("name", "").strip()
    note = request.form.get("note", "").strip()
    if not name:
        flash("Name is required.", "warning")
        return redirect(url_for("faces"))
    face_id = create_face(name=name, is_authorized=True, note=note)
    flash(f"Created face '{name}'.", "success")
    return redirect(url_for("face_details", face_id=face_id))

@app.post("/faces/<int:face_id>/delete")
def faces_delete(face_id: int):
    ok = delete_face(face_id)
    flash("Face deleted." if ok else "Face not found.", "success" if ok else "warning")
    return redirect(url_for("faces"))


# ---- Training ----
@app.get("/training")
def training():
    _ensure_training_dirs()
    face_rows = _collect_face_dataset_rows()
    fire_stats = {
        "flame_count": _count_images(FIRE_FLAME_DIR),
        "non_flame_count": _count_images(FIRE_NON_FLAME_DIR),
    }
    fire_model = _read_fire_model_meta()
    return render_template(
        "training.html",
        face_rows=face_rows,
        face_target=FACE_TARGET_SAMPLES,
        face_min=FACE_MIN_SAMPLES,
        fire_stats=fire_stats,
        fire_model=fire_model,
    )


@app.get("/training/face/status")
def training_face_status():
    name = _safe_name(request.args.get("name", ""))
    if not name:
        return jsonify({"ok": False, "error": "Name is required."}), 400
    count = _face_count_for_name(name)
    return jsonify(
        {
            "ok": True,
            "name": name,
            "count": count,
            "min_required": FACE_MIN_SAMPLES,
            "target": FACE_TARGET_SAMPLES,
            "remaining": max(0, FACE_TARGET_SAMPLES - count),
            "ready": count >= FACE_MIN_SAMPLES,
        }
    )


@app.post("/training/face/capture")
def training_face_capture():
    _ensure_training_dirs()
    payload = request.get_json(silent=True) or {}
    name = _safe_name(payload.get("name", ""))
    image_data = payload.get("image", "")

    if not name:
        return jsonify({"ok": False, "error": "Name is required."}), 400

    frame = _decode_data_url_image(image_data)
    if frame is None:
        return jsonify({"ok": False, "error": "Invalid frame payload."}), 400

    face_roi = extract_face_roi(frame)
    validation_error = _validate_face_roi(face_roi)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error}), 422
    return jsonify(_save_face_sample(name, face_roi))


@app.post("/training/face/capture_pi")
def training_face_capture_pi():
    _ensure_training_dirs()
    payload = request.get_json(silent=True) or {}
    name = _safe_name(payload.get("name", ""))
    source_raw = str(payload.get("source", "0")).strip()
    if not name:
        return jsonify({"ok": False, "error": "Name is required."}), 400

    cap = cv2.VideoCapture(_coerce_capture_source(source_raw))
    if not cap.isOpened():
        return jsonify({"ok": False, "error": f"Cannot open source: {source_raw or '0'}"}), 400

    frame = None
    for _ in range(6):
        ok, candidate = cap.read()
        if ok and candidate is not None:
            frame = candidate
    cap.release()

    if frame is None:
        return jsonify({"ok": False, "error": "Failed to read frame from external source."}), 422

    face_roi = extract_face_roi(frame)
    validation_error = _validate_face_roi(face_roi)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error}), 422
    return jsonify(_save_face_sample(name, face_roi))


@app.post("/training/face/train")
def training_face_train():
    ok, msg = _run_face_training()
    if ok:
        flash("LBPH retraining complete. Runtime will reload model automatically.", "success")
    else:
        flash("Face training failed:\n" + (msg[:900] + ("..." if len(msg) > 900 else "")), "warning")
    return redirect(url_for("training"))


@app.post("/training/fire/upload")
def training_fire_upload():
    _ensure_training_dirs()
    label = request.form.get("label", "").strip().lower()
    if label not in ("flame", "non_flame"):
        flash("Choose fire label: flame or non_flame.", "warning")
        return redirect(url_for("training"))

    files = request.files.getlist("images")
    if not files:
        flash("No images uploaded.", "warning")
        return redirect(url_for("training"))

    out_dir = FIRE_FLAME_DIR if label == "flame" else FIRE_NON_FLAME_DIR
    saved = 0
    for file_obj in files:
        if not file_obj or not file_obj.filename:
            continue
        raw = file_obj.read()
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            continue

        h, w = img.shape[:2]
        max_side = max(h, w)
        if max_side > 640:
            scale = 640.0 / float(max_side)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        base = _safe_name(os.path.splitext(file_obj.filename)[0]).replace(" ", "_")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        out_name = f"{ts}_{base or 'img'}.jpg"
        out_path = os.path.join(out_dir, out_name)
        if cv2.imwrite(out_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 88]):
            saved += 1

    if saved == 0:
        flash("No valid images were saved.", "warning")
    else:
        flash(f"Saved {saved} {label} image(s).", "success")
    return redirect(url_for("training"))


@app.post("/training/fire/train")
def training_fire_train():
    ok, msg = _run_fire_training()
    if ok:
        flash("Fire model training complete.", "success")
    else:
        flash("Fire training failed:\n" + (msg[:900] + ("..." if len(msg) > 900 else "")), "warning")
    return redirect(url_for("training"))

# ---- Health / Settings ----
@app.post("/settings/guest_mode")
def toggle_guest_mode():
    current = get_guest_mode()
    set_guest_mode(not current)
    flash(f"Guest Mode is now {'ON' if not current else 'OFF'}.", "success")
    return redirect(request.referrer or url_for("dashboard"))

@app.get("/health")
def health():
    nodes = list_node_status()
    return render_template("health.html", nodes=nodes)

@app.post("/seed/health")
def seed_health():
    update_node_seen("door_force", note="simulated")
    update_node_seen("mq2_living", note="simulated")
    update_node_seen("mq2_door", note="simulated")
    update_node_seen("cam_outdoor", note="simulated")
    update_node_seen("cam_indoor", note="simulated")
    flash("Seeded simulated node health entries.", "success")
    return redirect(url_for("health"))

# ---- Daily Summary ----
def _today_utc_date_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()

@app.get("/summary")
def summary():
    date_str = request.args.get("date", "").strip() or _today_utc_date_str()
    data = summary_for_date(date_str)

    # build a simple date picker list: last 14 days in UTC
    today = datetime.now(timezone.utc).date()
    date_options = [(today - timedelta(days=i)).isoformat() for i in range(0, 14)]
    return render_template("summary.html", data=data, date_str=date_str, date_options=date_options)

@app.get("/summary.csv")
def summary_csv():
    date_str = request.args.get("date", "").strip() or _today_utc_date_str()
    data = summary_for_date(date_str)

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", data["date"]])
    w.writerow(["window_start", data["start"]])
    w.writerow(["window_end", data["end"]])
    w.writerow([])

    w.writerow(["ALERTS by type/status"])
    w.writerow(["type", "status", "count"])
    for r in data["alerts_by_type_status"]:
        w.writerow([r["type"], r["status"], r["c"]])
    w.writerow([])

    w.writerow(["ALERTS by status"])
    w.writerow(["status", "count"])
    for r in data["alerts_by_status"]:
        w.writerow([r["status"], r["c"]])
    w.writerow([])

    w.writerow(["EVENTS by type"])
    w.writerow(["type", "count"])
    for r in data["events_by_type"]:
        w.writerow([r["type"], r["c"]])
    w.writerow([])

    w.writerow(["SNAPSHOTS by type/label"])
    w.writerow(["type", "label", "count"])
    for r in data["snapshots_by_type_label"]:
        w.writerow([r["type"], r["label"], r["c"]])
    w.writerow([])

    w.writerow(["TOP ROOMS (alerts)"])
    w.writerow(["room", "count"])
    for r in data["top_rooms"]:
        w.writerow([r["room"], r["c"]])

    resp = Response(out.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="summary_{date_str}.csv"'
    return resp

@app.get("/summary.html")
def summary_html_export():
    date_str = request.args.get("date", "").strip() or _today_utc_date_str()
    data = summary_for_date(date_str)
    # Minimal standalone HTML export using the same template but export mode
    html = render_template("summary_export.html", data=data, date_str=date_str)
    resp = Response(html, mimetype="text/html; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="summary_{date_str}.html"'
    return resp


@app.post("/faces/retrain")
def faces_retrain():
    ok, msg = _run_face_training()
    if ok:
        flash("LBPH retraining complete. Runtime will reload model automatically.", "success")
    else:
        flash("Face training failed:\n" + (msg[:900] + ("..." if len(msg) > 900 else "")), "warning")
    return redirect(request.referrer or url_for("faces"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
