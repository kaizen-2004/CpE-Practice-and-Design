from flask import Flask, redirect, render_template, request, url_for, flash, send_from_directory, abort, Response, jsonify
import csv
import io
import json
import base64
import re
from datetime import datetime, timezone, timedelta
import time
import atexit
import os
import sys
import subprocess
import threading
from typing import Optional
from urllib import request as urllib_request
from zoneinfo import ZoneInfo

import cv2
import numpy as np
try:
    import paho.mqtt.publish as mqtt_publish
except Exception:
    mqtt_publish = None

def _load_local_env() -> None:
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                os.environ[key] = value
    except OSError:
        return

_load_local_env()

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
    create_alert,
    has_recent_alert,
)
from vision_utils import (
    export_face_sample_from_snapshot,
    detect_preprocess_faces,
    analyze_faces,
    draw_face_detections,
)
from config import (
    ROOMS,
    NODE_META,
    NODE_OFFLINE_SECONDS,
    MQTT_TOPIC_ROOT,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_BROKER_USERNAME,
    MQTT_BROKER_PASSWORD,
    normalize_node_id,
    get_node_meta,
    EVENT_SMOKE_HIGH,
    EVENT_DOOR_FORCE,
    EVENT_FLAME_SIGNAL,
    EVENT_UNKNOWN,
)
from fusion import handle_fire_signal, handle_intruder_evidence, handle_door_force_signal
from notifications import TelegramAlertNotifier, telegram_is_configured, send_telegram_test_message

app = Flask(__name__)
app.secret_key = "dev-only-change-me"  # change later for real deployments

MINIMAL_CORE_MODE = True
CORE_ENDPOINTS = {
    "home",
    "dashboard",
    "dashboard_legacy",
    "dashboard_live",
    "ui_nodes_live",
    "ui_events_live",
    "ui_camera_control",
    "ui_stats_daily",
    "ui_settings_live",
    "api_faces_list",
    "api_faces_create",
    "api_faces_delete",
    "api_training_face_status",
    "api_training_face_capture",
    "api_training_face_train",
    "alert_details",
    "ack",
    "history",
    "events",
    "sensors_event",
    "camera_proxy",
    "camera_frame",
    "camera_local_frame",
    "camera_local_stream",
    "camera_processed_frame",
    "camera_processed_stream",
    "serve_snapshot",
    "service_worker",
    "web_manifest",
    "static",
}

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REACT_DASHBOARD_DIST_DIR = os.path.join(PROJECT_ROOT, "web_dashboard_ui", "dist")
REACT_DASHBOARD_INDEX = os.path.join(REACT_DASHBOARD_DIST_DIR, "index.html")
REACT_DASHBOARD_ENABLED = os.environ.get("REACT_DASHBOARD_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "faces")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
FIRE_DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "fire")
FIRE_FLAME_DIR = os.path.join(FIRE_DATASET_DIR, "flame")
FIRE_NON_FLAME_DIR = os.path.join(FIRE_DATASET_DIR, "non_flame")
FIRE_MODEL_PATH = os.path.join(MODELS_DIR, "fire_color.json")
LBPH_MODEL_PATH = os.path.join(MODELS_DIR, "lbph.yml")
LBPH_LABELS_PATH = os.path.join(MODELS_DIR, "labels.json")
FACE_TARGET_SAMPLES = int(os.environ.get("FACE_TARGET_SAMPLES", "24"))
FACE_MIN_SAMPLES = int(os.environ.get("FACE_MIN_SAMPLES", "16"))
FACE_UNKNOWN_THRESHOLD = float(os.environ.get("UNKNOWN_THRESHOLD", "65"))


init_db()

_TELEGRAM_NOTIFIER = TelegramAlertNotifier(app.logger)
_TELEGRAM_NOTIFIER.start()
atexit.register(_TELEGRAM_NOTIFIER.stop)

_FACE_MODEL_LOCK = threading.RLock()
_FACE_MODEL_CACHE = {
    "version": None,
    "recognizer": None,
    "id_to_name": {},
}

EVENT_LABELS = {
    "DOOR_HEARTBEAT": "Door Sensor Check-In",
    "DOOR_SENSOR_OFFLINE": "Door Sensor Offline",
    "DOOR_FORCE": "Door Impact Detected",
    "SMOKE_HEARTBEAT": "Smoke Sensor Check-In",
    "SMOKE_SENSOR_OFFLINE": "Smoke Sensor Offline",
    "SMOKE_HIGH": "Smoke Warning",
    "SMOKE_NORMAL": "Smoke Level Back to Normal",
    "NODE_HEARTBEAT": "Node Check-In",
    "NODE_OFFLINE": "Node Offline",
    "CAM_HEARTBEAT": "Camera Check-In",
    "CAMERA_OFFLINE": "Camera Offline",
    "CAM_CONTROL_ACK": "Camera Control Acknowledgement",
    "VISION_HEARTBEAT": "Vision Runtime Check-In",
    "FLAME_SIGNAL": "Possible Flame Detected",
    "UNKNOWN": "Unknown Person Detected",
    "AUTHORIZED": "Authorized Person Detected",
}

ALERT_LABELS = {
    "DOOR_FORCE": "Door Force Alert",
    "DOOR_SENSOR_OFFLINE": "Door Sensor Disconnected",
    "INTRUDER": "Intrusion Alert",
    "FIRE": "Fire Alert",
}

STATUS_LABELS = {
    "ACTIVE": "Active",
    "ACK": "Acknowledged",
    "RESOLVED": "Resolved",
}

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


def _display_timezone():
    tz_name = os.environ.get("DISPLAY_TIMEZONE", "Asia/Manila").strip()
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def _format_display_time(ts: str, short: bool = False) -> str:
    if not ts:
        return "-"
    dt = _parse_iso(str(ts))
    if not dt:
        return str(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_dt = dt.astimezone(_display_timezone())
    time_part = local_dt.strftime("%I:%M %p").lstrip("0") or local_dt.strftime("%I:%M %p")
    date_short = f"{local_dt.strftime('%b')} {local_dt.day}"
    if short:
        return f"{date_short}, {time_part}"
    return f"{date_short}, {local_dt.year}, {time_part}"


def _friendly_label(raw: str, labels: dict[str, str]) -> str:
    key = str(raw or "").strip().upper()
    if not key:
        return "-"
    if key in labels:
        return labels[key]
    return key.replace("_", " ").title()


def _friendly_event_label(event_type: str) -> str:
    return _friendly_label(event_type, EVENT_LABELS)


def _friendly_alert_label(alert_type: str) -> str:
    return _friendly_label(alert_type, ALERT_LABELS)


def _friendly_status_label(status: str) -> str:
    return _friendly_label(status, STATUS_LABELS)


def _friendly_source_label(source: str) -> str:
    if not source:
        return "-"
    node_id = normalize_node_id(source)
    meta = get_node_meta(node_id)
    if meta.get("label"):
        return meta["label"]
    raw = str(source).strip()
    return raw.replace("_", " ").replace("-", " ").title()


def _parse_detail_segments(details: str) -> list[str]:
    return [seg.strip() for seg in str(details or "").split("|") if seg.strip()]


def _parse_detail_fields(details: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for seg in _parse_detail_segments(details):
        if seg.startswith("value="):
            fields["value_raw"] = seg[len("value="):].strip()
            continue
        for token in seg.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            key = key.strip().lower()
            value = value.strip().strip(",")
            if key and value:
                fields[key] = value
    return fields


def _extract_value_and_unit(details: str) -> tuple[str, str]:
    value_raw = _parse_detail_fields(details).get("value_raw", "")
    if not value_raw:
        return "", ""
    match = re.match(r"^([-+]?\d+(?:\.\d+)?)(.*)$", value_raw)
    if not match:
        return value_raw, ""
    return match.group(1), match.group(2).strip()


def _join_phrases(parts: list[str]) -> str:
    cleaned = [part.strip().rstrip(".") for part in parts if part and part.strip()]
    if not cleaned:
        return "-"
    return ". ".join(cleaned) + "."


def _friendly_measurement(event_type: str, details: str, fields: dict[str, str]) -> str:
    value, unit = _extract_value_and_unit(details)
    if not value:
        value = fields.get("ratio", "")
        unit = "ratio" if value and not unit else unit
    if not value:
        return ""

    event_key = str(event_type or "").upper()
    if event_key == "DOOR_HEARTBEAT":
        return f"Baseline reading: {value} g"
    if event_key == "DOOR_FORCE":
        return f"Trigger score: {value}"
    if event_key in ("SMOKE_HEARTBEAT", "SMOKE_HIGH", "SMOKE_NORMAL"):
        return f"Sensor reading: {value}"
    if event_key == "FLAME_SIGNAL":
        return f"Detection score: {value}"
    if unit:
        return f"Reading: {value} {unit.replace('_', ' ')}"
    return f"Reading: {value}"


def _friendly_event_summary(event_type: str, details: str, source: str = "") -> str:
    raw_details = str(details or "").strip()
    if not raw_details:
        return _friendly_event_label(event_type)

    fields = _parse_detail_fields(raw_details)
    event_key = str(event_type or "").upper()

    if event_key == "DOOR_HEARTBEAT":
        parts = ["Door sensor is online"]
        if fields.get("imu") == "offline":
            parts.append("Motion chip is not ready yet")
        elif fields.get("calibrated") == "no":
            parts.append("Sensor is still calibrating")
        measurement = _friendly_measurement(event_key, raw_details, fields)
        if measurement:
            parts.append(measurement)
        return _join_phrases(parts)

    if event_key == "DOOR_FORCE":
        parts = ["Door impact or forced movement was detected"]
        measurement = _friendly_measurement(event_key, raw_details, fields)
        if measurement:
            parts.append(measurement)
        return _join_phrases(parts)

    if event_key == "DOOR_SENSOR_OFFLINE":
        return "Door sensor went offline or was disconnected."

    if event_key == "SMOKE_HEARTBEAT":
        parts = ["Smoke sensor is online"]
        if fields.get("latched") == "1":
            parts.append("Smoke warning remains latched")
        measurement = _friendly_measurement(event_key, raw_details, fields)
        if measurement:
            parts.append(measurement)
        return _join_phrases(parts)

    if event_key == "SMOKE_HIGH":
        parts = ["Smoke level rose above the warning threshold"]
        measurement = _friendly_measurement(event_key, raw_details, fields)
        if measurement:
            parts.append(measurement)
        return _join_phrases(parts)

    if event_key == "SMOKE_NORMAL":
        parts = ["Smoke level returned to a safer range"]
        measurement = _friendly_measurement(event_key, raw_details, fields)
        if measurement:
            parts.append(measurement)
        return _join_phrases(parts)

    if event_key == "SMOKE_SENSOR_OFFLINE":
        return "Smoke sensor went offline or was disconnected."

    if event_key == "CAMERA_OFFLINE":
        return "Camera node went offline or was disconnected."

    if event_key == "NODE_OFFLINE":
        return "A sensor or camera node went offline."

    if event_key == "FLAME_SIGNAL":
        parts = ["Indoor camera detected a possible flame"]
        measurement = _friendly_measurement(event_key, raw_details, fields)
        if measurement:
            parts.append(measurement)
        return _join_phrases(parts)

    if event_key == "UNKNOWN":
        faces = fields.get("faces", "")
        unknown_count = fields.get("unknown", "")
        parts = ["An unknown person was detected"]
        if faces and faces.isdigit() and int(faces) > 1:
            parts.append(f"Faces seen: {faces}")
        elif unknown_count and unknown_count.isdigit() and int(unknown_count) > 1:
            parts[0] = "Unknown people were detected"
            parts.append(f"Unrecognized faces: {unknown_count}")
        return _join_phrases(parts)

    if event_key == "AUTHORIZED":
        names = [name.strip().replace("_", " ").title() for name in fields.get("known", "").split(",") if name.strip()]
        if names:
            lead = "Authorized person detected" if len(names) == 1 else "Authorized people detected"
            return _join_phrases([lead, ", ".join(names)])
        faces = fields.get("faces", "")
        if faces and faces.isdigit():
            return _join_phrases(["Authorized face detected", f"Faces seen: {faces}"])
        return _join_phrases(["Authorized person detected"])

    if raw_details.startswith("threshold_crossed"):
        return "Smoke level rose above the warning threshold."
    if raw_details.startswith("returned_below_clear_threshold"):
        return "Smoke level returned to a safer range."

    return raw_details.replace("|", ". ").strip()


def _friendly_alert_summary(alert_type: str, details: str) -> str:
    raw_details = str(details or "").strip()
    if not raw_details:
        return _friendly_alert_label(alert_type)

    alert_key = str(alert_type or "").upper()
    if alert_key == "INTRUDER" and raw_details.startswith("Evidence:"):
        evidence_text = raw_details.split(":", 1)[1].strip()
        mapped = []
        for item in [part.strip() for part in evidence_text.split(",") if part.strip()]:
            if item == "outdoor unknown":
                mapped.append("outdoor camera saw an unknown person")
            elif item == "indoor unknown":
                mapped.append("indoor camera saw an unknown person")
            elif item == "door-force":
                mapped.append("door sensor detected impact")
            else:
                mapped.append(item.replace("-", " "))
        if mapped:
            return _join_phrases(["Multiple intrusion signs matched", ", ".join(mapped)])

    if alert_key == "FIRE" and raw_details.startswith("Fusion:"):
        return "Smoke sensor and indoor flame detection were both triggered."

    if alert_key == "DOOR_FORCE":
        return _friendly_event_summary("DOOR_FORCE", raw_details)

    if alert_key == "DOOR_SENSOR_OFFLINE":
        return _friendly_event_summary("DOOR_SENSOR_OFFLINE", raw_details)

    return raw_details.replace("|", ". ").strip()


def _severity_label(severity: int) -> str:
    try:
        level = int(severity)
    except Exception:
        level = 0
    if level >= 3:
        return "High"
    if level == 2:
        return "Medium"
    return "Low"


def _dashboard_node_counts() -> dict[str, int]:
    node_rows = list_node_status()
    node_map = {n["node"]: n for n in node_rows}

    sensors_total = 0
    sensors_online = 0
    cameras_total = 0
    cameras_online = 0

    for node_id, meta in NODE_META.items():
        if meta.get("kind") == "sensor":
            sensors_total += 1
            row = node_map.get(node_id)
            if row and _is_online(row["last_seen_ts"]):
                sensors_online += 1
        elif meta.get("kind") == "camera":
            cameras_total += 1
            row = node_map.get(node_id)
            if row and _is_online(row["last_seen_ts"]):
                cameras_online += 1

    return {
        "sensors_total": sensors_total,
        "sensors_online": sensors_online,
        "cameras_total": cameras_total,
        "cameras_online": cameras_online,
    }


def _serialize_alert_row(row) -> dict:
    return {
        "id": int(row["id"]),
        "type": str(row["type"] or ""),
        "type_label": _friendly_alert_label(row["type"]),
        "room": str(row["room"] or "-"),
        "severity": int(row["severity"] or 0),
        "severity_label": _severity_label(int(row["severity"] or 0)),
        "status": str(row["status"] or ""),
        "status_label": _friendly_status_label(row["status"]),
        "time_label": _format_display_time(row["ts"]),
        "summary": _friendly_alert_summary(row["type"], row["details"]),
        "details": str(row["details"] or ""),
        "detail_url": url_for("alert_details", alert_id=int(row["id"])),
        "ack_url": url_for("ack", alert_id=int(row["id"])),
    }


def _serialize_event_row(row) -> dict:
    return {
        "id": int(row["id"]),
        "type": str(row["type"] or ""),
        "type_label": _friendly_event_label(row["type"]),
        "source": str(row["source"] or ""),
        "source_label": _friendly_source_label(row["source"]),
        "room": str(row["room"] or "-"),
        "time_label": _format_display_time(row["ts"]),
        "summary": _friendly_event_summary(row["type"], row["details"], row["source"]),
        "details": str(row["details"] or ""),
    }


def _ui_event_type_from_code(code: str) -> str:
    key = str(code or "").upper()
    if key in ("INTRUDER", "UNKNOWN", "DOOR_FORCE"):
        return "intruder"
    if key in ("FIRE", "FLAME_SIGNAL", "SMOKE_HIGH", "SMOKE_NORMAL"):
        return "fire" if key in ("FIRE", "FLAME_SIGNAL") else "sensor"
    if key == "AUTHORIZED":
        return "authorized"
    return "system" if "HEARTBEAT" in key else "sensor"


def _ui_severity_from_level(level: int) -> str:
    try:
        value = int(level)
    except Exception:
        value = 1
    if value >= 3:
        return "critical"
    if value == 2:
        return "warning"
    if value <= 0:
        return "info"
    return "normal"


def _ui_alert_from_alert_row(row) -> dict:
    alert_type = str(row["type"] or "").upper()
    event_code = alert_type
    if alert_type in ("INTRUDER", "FIRE"):
        event_code = alert_type
    severity = _ui_severity_from_level(int(row["severity"] or 1))
    source_guess = "cam_outdoor" if (row["room"] or "") == "Door Entrance Area" else "cam_indoor"
    return {
        "id": f"alert-{int(row['id'])}",
        "timestamp": str(row["ts"] or ""),
        "severity": severity,
        "type": _ui_event_type_from_code(event_code),
        "event_code": event_code,
        "source_node": source_guess,
        "location": str(row["room"] or "Door Entrance Area"),
        "title": _friendly_alert_label(row["type"]),
        "description": _friendly_alert_summary(row["type"], row["details"]),
        "acknowledged": str(row["status"] or "").upper() != "ACTIVE",
        "confidence": None,
        "response_time_ms": None,
        "fusion_evidence": [],
    }


def _ui_event_from_event_row(row) -> dict:
    event_code = str(row["type"] or "").upper()
    source_raw = str(row["source"] or "")
    source_guess = source_raw.lower()
    if source_raw == "CAM_OUTDOOR":
        source_guess = "cam_outdoor"
    elif source_raw == "CAM_INDOOR":
        source_guess = "cam_indoor"
    elif source_guess == "":
        source_guess = "unknown"
    return {
        "id": f"event-{int(row['id'])}",
        "timestamp": str(row["ts"] or ""),
        "severity": "info" if "HEARTBEAT" in event_code else (
            "warning"
            if event_code in ("DOOR_FORCE", "SMOKE_HIGH", "FLAME_SIGNAL", "DOOR_SENSOR_OFFLINE", "SMOKE_SENSOR_OFFLINE", "CAMERA_OFFLINE", "NODE_OFFLINE")
            else "normal"
        ),
        "type": _ui_event_type_from_code(event_code),
        "event_code": event_code,
        "source_node": source_guess,
        "location": str(row["room"] or "Door Entrance Area"),
        "title": _friendly_event_label(row["type"]),
        "description": _friendly_event_summary(row["type"], row["details"], row["source"]),
        "acknowledged": True,
        "confidence": None,
        "response_time_ms": None,
        "fusion_evidence": [],
    }


def _runtime_uptime_label() -> str:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as fh:
            total_seconds = int(float((fh.read().split() or ["0"])[0]))
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m"
    except Exception:
        return "-"


def _camera_control_topic(node_id: str) -> str:
    return f"{MQTT_TOPIC_ROOT}/camera/{normalize_node_id(node_id)}/control"


def _publish_camera_control(node_id: str, command: str) -> tuple[bool, str, str]:
    topic = _camera_control_topic(node_id)
    payload = json.dumps({"cmd": command}, separators=(",", ":"))
    if mqtt_publish is None:
        return False, "paho-mqtt is not installed", topic

    auth = None
    if MQTT_BROKER_USERNAME:
        auth = {"username": MQTT_BROKER_USERNAME, "password": MQTT_BROKER_PASSWORD}

    try:
        mqtt_publish.single(
            topic,
            payload=payload,
            qos=1,
            retain=False,
            hostname=MQTT_BROKER_HOST or "127.0.0.1",
            port=int(MQTT_BROKER_PORT),
            auth=auth,
            keepalive=20,
            client_id=f"ui-camctl-{int(time.time())}",
        )
        return True, "", topic
    except Exception as exc:
        app.logger.warning("camera control publish failed node=%s command=%s error=%s", node_id, command, exc)
        return False, str(exc), topic


def _ui_profile_from_face_row(row) -> dict:
    created_ts = str(row["created_ts"] or "")
    enrolled = created_ts.split("T")[0] if "T" in created_ts else created_ts
    return {
        "id": f"auth-{int(row['id'])}",
        "db_id": int(row["id"]),
        "label": str(row["name"] or f"Face {int(row['id'])}"),
        "role": "Authorized",
        "enrolled_at": enrolled or "-",
        "sample_count": int(row["sample_count"] or 0),
    }


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

def _extract_training_face(frame_bgr):
    candidates = detect_preprocess_faces(frame_bgr)
    if not candidates:
        return None, 0, None
    best = candidates[0]
    return best["roi"], len(candidates), best["rect"]

def _face_model_version():
    if not (os.path.exists(LBPH_MODEL_PATH) and os.path.exists(LBPH_LABELS_PATH)):
        return None
    return (
        os.path.getmtime(LBPH_MODEL_PATH),
        os.path.getmtime(LBPH_LABELS_PATH),
    )

def _load_face_model_from_disk():
    if _face_model_version() is None:
        return None, {}
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except Exception:
        return None, {}
    try:
        recognizer.read(LBPH_MODEL_PATH)
        with open(LBPH_LABELS_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        id_to_name = {int(k): str(v) for k, v in (meta.get("id_to_name", {}) or {}).items()}
        return recognizer, id_to_name
    except Exception:
        return None, {}

def _get_face_model():
    version = _face_model_version()
    with _FACE_MODEL_LOCK:
        if version != _FACE_MODEL_CACHE["version"]:
            recognizer, id_to_name = _load_face_model_from_disk()
            _FACE_MODEL_CACHE["version"] = version
            _FACE_MODEL_CACHE["recognizer"] = recognizer
            _FACE_MODEL_CACHE["id_to_name"] = id_to_name
        return _FACE_MODEL_CACHE["recognizer"], dict(_FACE_MODEL_CACHE["id_to_name"])

def _annotate_face_frame(frame_bgr):
    recognizer, id_to_name = _get_face_model()
    with _FACE_MODEL_LOCK:
        detections = analyze_faces(
            frame_bgr,
            recognizer=recognizer,
            id_to_name=id_to_name,
            unknown_threshold=FACE_UNKNOWN_THRESHOLD,
        )
    return draw_face_detections(frame_bgr, detections), detections

def _annotate_face_jpeg(jpeg_bytes: bytes) -> bytes:
    if not jpeg_bytes:
        return jpeg_bytes
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg_bytes
    annotated, _ = _annotate_face_frame(frame)
    if annotated is None:
        return jpeg_bytes
    ok, enc = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), _local_camera_jpeg_quality()])
    if not ok:
        return jpeg_bytes
    return enc.tobytes()


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
        "telegram_enabled": telegram_is_configured(),
        "minimal_core_mode": MINIMAL_CORE_MODE,
        "format_ts": _format_display_time,
        "event_label": _friendly_event_label,
        "alert_label": _friendly_alert_label,
        "status_label": _friendly_status_label,
        "source_label": _friendly_source_label,
        "event_summary": _friendly_event_summary,
        "alert_summary": _friendly_alert_summary,
    }


@app.before_request
def minimal_core_guard():
    if not MINIMAL_CORE_MODE:
        return None

    endpoint = request.endpoint or ""
    if endpoint in CORE_ENDPOINTS or endpoint.startswith("static"):
        return None

    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Endpoint disabled in minimal-core-system branch"}), 404

    if request.method == "GET":
        flash("This page is disabled in the minimal-core-system branch.", "warning")
    else:
        flash("This action is disabled in the minimal-core-system branch.", "warning")
    return redirect(request.referrer or url_for("dashboard"))


def _react_dashboard_ready() -> bool:
    return REACT_DASHBOARD_ENABLED and os.path.isfile(REACT_DASHBOARD_INDEX)


def _serve_react_dashboard(spa_path: str = ""):
    requested = str(spa_path or "").lstrip("/")
    dist_root = os.path.abspath(REACT_DASHBOARD_DIST_DIR)
    if requested:
        candidate = os.path.abspath(os.path.join(dist_root, requested))
        if candidate.startswith(dist_root + os.sep) and os.path.isfile(candidate):
            return send_from_directory(dist_root, requested)
    return send_from_directory(dist_root, "index.html")


def _render_dashboard_template():
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
    outdoor_local_source = _local_camera_source_for("outdoor")
    indoor_local_source = _local_camera_source_for("indoor")
    # Avoid rendering the same local capture device as two different cameras.
    if (
        outdoor_local_source
        and indoor_local_source
        and _coerce_capture_source(outdoor_local_source) == _coerce_capture_source(indoor_local_source)
    ):
        outdoor_local_source = ""
    outdoor_src = _camera_url_for("outdoor")
    indoor_src = _camera_url_for("indoor")

    # Prefer explicit network stream URL for outdoor camera when available.
    if outdoor_src:
        outdoor_url = url_for("camera_frame", which="outdoor")
        outdoor_mode = "Network Camera"
        outdoor_is_stream = False
    elif outdoor_local_source:
        outdoor_url = url_for("camera_local_stream", which="outdoor")
        outdoor_mode = "USB Camera"
        outdoor_is_stream = True
    else:
        outdoor_url = ""
        outdoor_mode = "Not Connected"
        outdoor_is_stream = False

    if indoor_src:
        indoor_url = url_for("camera_frame", which="indoor")
        indoor_mode = "Network Camera"
        indoor_is_stream = False
    elif indoor_local_source:
        indoor_url = url_for("camera_local_stream", which="indoor")
        indoor_mode = "USB Camera"
        indoor_is_stream = True
    else:
        indoor_url = ""
        indoor_mode = "Not Connected"
        indoor_is_stream = False

    camera_refresh_ms = int(os.environ.get("CAMERA_REFRESH_MS", "900"))
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
        outdoor_mode=outdoor_mode,
        indoor_mode=indoor_mode,
        outdoor_is_stream=outdoor_is_stream,
        indoor_is_stream=indoor_is_stream,
        camera_refresh_ms=max(400, camera_refresh_ms),
    )


@app.get("/")
def home():
    return redirect(url_for("dashboard"))


@app.get("/service-worker.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "service-worker.js")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/manifest.webmanifest")
def web_manifest():
    resp = send_from_directory(app.static_folder, "manifest.webmanifest")
    resp.headers["Cache-Control"] = "no-cache"
    return resp

# ---- Camera Proxy ----
def _extract_stream_url_from_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""

    full_url = re.search(r"stream=(https?://[^\s|]+)", text)
    if full_url:
        return full_url.group(1).strip()

    ip_match = re.search(r"\bip=([0-9]{1,3}(?:\.[0-9]{1,3}){3})\b", text)
    if not ip_match:
        return ""
    host = ip_match.group(1).strip()

    stream_match = re.search(r"stream=([^\s|]+)", text)
    if stream_match:
        stream_raw = stream_match.group(1).strip()
        if stream_raw.startswith(("http://", "https://")):
            return stream_raw
        if stream_raw.startswith(":") or stream_raw.startswith("/"):
            return f"http://{host}{stream_raw}"

    return f"http://{host}:81/stream"


def _camera_url_from_recent_events(node_id: str) -> str:
    node_key = normalize_node_id(node_id)
    source = "CAM_OUTDOOR" if node_key == "cam_outdoor" else "CAM_INDOOR" if node_key == "cam_indoor" else ""
    if not source:
        return ""
    try:
        rows = list_recent_events(limit=240)
    except Exception:
        return ""

    for row in rows:
        if str(row["source"] or "").strip().upper() != source:
            continue
        url = _extract_stream_url_from_text(str(row["details"] or ""))
        if url:
            return url
    return ""


def _camera_url_from_node_note(node_id: str) -> str:
    node_key = normalize_node_id(node_id)
    try:
        rows = list_node_status()
    except Exception:
        return ""

    note = ""
    for row in rows:
        row_node = normalize_node_id(str(row["node"] or ""))
        if row_node == node_key:
            note = str(row["note"] or "")
            break
    url = _extract_stream_url_from_text(note)
    if url:
        return url
    return _camera_url_from_recent_events(node_id)


def _camera_url_for(which: str) -> str:
    if which == "outdoor":
        explicit = os.environ.get("OUTDOOR_URL", "").strip()
        return explicit or _camera_url_from_node_note("cam_outdoor")
    if which == "indoor":
        explicit = os.environ.get("INDOOR_URL", "").strip()
        return explicit or _camera_url_from_node_note("cam_indoor")
    return ""

def _fetch_single_jpeg(src_url: str, timeout_seconds: float = 6.0) -> Optional[bytes]:
    req = urllib_request.Request(src_url, headers={"User-Agent": "CondoCameraProxy/1.0"})
    started = time.time()
    buf = b""
    with urllib_request.urlopen(req, timeout=timeout_seconds) as upstream:
        while (time.time() - started) < timeout_seconds:
            chunk = upstream.read(4096)
            if not chunk:
                break
            buf += chunk
            soi = buf.find(b"\xff\xd8")
            if soi != -1:
                eoi = buf.find(b"\xff\xd9", soi + 2)
                if eoi != -1:
                    return buf[soi:eoi + 2]
            if len(buf) > 2_000_000:
                buf = buf[-256_000:]
    return None


def _local_camera_source_for(which: str) -> str:
    source = ""
    if which == "outdoor":
        source = os.environ.get("OUTDOOR_CAM_SOURCE", "").strip()
    elif which == "indoor":
        source = os.environ.get("INDOOR_CAM_SOURCE", "").strip()
    if source.lower() in ("", "none", "off", "-"):
        return ""
    return source


def _camera_capture_source_for(which: str) -> str:
    local_source = _local_camera_source_for(which)
    if local_source:
        return local_source
    return _camera_url_for(which)


def _open_camera_capture(source_raw: str):
    source = _coerce_capture_source(source_raw)
    is_local_device = isinstance(source, int)
    if isinstance(source, str) and source.startswith("/dev/video"):
        is_local_device = True
    if is_local_device:
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        if cap.isOpened():
            return cap
        cap.release()
    return cv2.VideoCapture(source)


def _encode_annotated_frame(frame_bgr) -> Optional[bytes]:
    if frame_bgr is None:
        return None
    annotated, _ = _annotate_face_frame(frame_bgr)
    out = annotated if annotated is not None else frame_bgr
    ok, enc = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), _local_camera_jpeg_quality()])
    if not ok:
        return None
    return enc.tobytes()


def _local_camera_jpeg_quality() -> int:
    try:
        value = int(os.environ.get("LOCAL_CAM_JPEG_QUALITY", "80"))
    except Exception:
        value = 80
    return max(40, min(95, value))


def _local_camera_retry_seconds() -> float:
    try:
        value = float(os.environ.get("LOCAL_CAM_RETRY_SECONDS", "2.0"))
    except Exception:
        value = 2.0
    return max(0.5, min(10.0, value))


def _local_stream_fps() -> float:
    try:
        value = float(os.environ.get("LOCAL_STREAM_FPS", "12"))
    except Exception:
        value = 12.0
    return max(2.0, min(30.0, value))


def _processed_stream_fps() -> float:
    try:
        value = float(os.environ.get("PROCESSED_STREAM_FPS", "8"))
    except Exception:
        value = 8.0
    return max(2.0, min(20.0, value))


class _LocalCameraWorker:
    def __init__(self, which: str, source_raw: str):
        self.which = which
        self.source_raw = source_raw
        self.source = _coerce_capture_source(source_raw)
        self._lock = threading.Lock()
        self._latest_jpeg: Optional[bytes] = None
        self._last_frame_ts = 0.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"cam-{self.which}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.5)

    def latest_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_jpeg

    def latest_frame_with_ts(self):
        with self._lock:
            return self._latest_jpeg, self._last_frame_ts

    def _open_capture(self):
        is_local_device = isinstance(self.source, int)
        if isinstance(self.source, str) and self.source.startswith("/dev/video"):
            is_local_device = True
        if is_local_device:
            cap = cv2.VideoCapture(self.source, cv2.CAP_V4L2)
            if cap.isOpened():
                return cap
            cap.release()
        return cv2.VideoCapture(self.source)

    def _run(self) -> None:
        cap = None
        jpeg_quality = _local_camera_jpeg_quality()
        retry_seconds = _local_camera_retry_seconds()
        encode_opts = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        fail_count = 0
        while not self._stop_event.is_set():
            try:
                if cap is None or not cap.isOpened():
                    cap = self._open_capture()
                    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        fail_count += 1
                        if fail_count == 1 or fail_count % 15 == 0:
                            app.logger.warning(
                                "Local camera '%s' unavailable at source '%s' (fail=%s).",
                                self.which,
                                self.source_raw,
                                fail_count,
                            )
                        time.sleep(retry_seconds)
                        continue
                    fail_count = 0
                    # Read a few frames first so auto-exposure settles.
                    for _ in range(4):
                        cap.read()

                ok, frame = cap.read()
                if not ok or frame is None:
                    fail_count += 1
                    if cap is not None:
                        cap.release()
                        cap = None
                    time.sleep(retry_seconds)
                    continue

                ok_jpeg, encoded = cv2.imencode(".jpg", frame, encode_opts)
                if not ok_jpeg:
                    continue

                with self._lock:
                    self._latest_jpeg = encoded.tobytes()
                    self._last_frame_ts = time.time()
            except Exception:
                fail_count += 1
                if cap is not None:
                    cap.release()
                    cap = None
                if fail_count == 1 or fail_count % 15 == 0:
                    app.logger.exception("Local camera '%s' crashed; retrying.", self.which)
                time.sleep(retry_seconds)

        if cap is not None:
            cap.release()


_LOCAL_CAMERA_WORKERS: dict[str, _LocalCameraWorker] = {}
_LOCAL_CAMERA_BINDINGS: dict[str, str] = {}
_LOCAL_CAMERA_WORKERS_LOCK = threading.Lock()

_PROCESSED_CAMERA_WORKERS: dict[str, "_ProcessedCameraWorker"] = {}
_PROCESSED_CAMERA_BINDINGS: dict[str, str] = {}
_PROCESSED_CAMERA_WORKERS_LOCK = threading.Lock()


def _get_local_camera_worker(which: str) -> Optional[_LocalCameraWorker]:
    source_raw = _local_camera_source_for(which)
    if not source_raw:
        return None
    with _LOCAL_CAMERA_WORKERS_LOCK:
        prev_source = _LOCAL_CAMERA_BINDINGS.get(which)
        if prev_source and prev_source != source_raw:
            _LOCAL_CAMERA_BINDINGS.pop(which, None)
            old_worker = _LOCAL_CAMERA_WORKERS.get(prev_source)
            if old_worker and prev_source not in _LOCAL_CAMERA_BINDINGS.values():
                old_worker.stop()
                _LOCAL_CAMERA_WORKERS.pop(prev_source, None)

        worker = _LOCAL_CAMERA_WORKERS.get(source_raw)
        if worker is None:
            worker = _LocalCameraWorker(which=which, source_raw=source_raw)
            worker.start()
            _LOCAL_CAMERA_WORKERS[source_raw] = worker
        _LOCAL_CAMERA_BINDINGS[which] = source_raw
        return worker


class _ProcessedCameraWorker:
    def __init__(self, which: str, source_raw: str):
        self.which = which
        self.source_raw = source_raw
        self._lock = threading.Lock()
        self._latest_jpeg: Optional[bytes] = None
        self._last_frame_ts = 0.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"cam-processed-{self.which}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.5)

    def latest_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_jpeg

    def latest_frame_with_ts(self):
        with self._lock:
            return self._latest_jpeg, self._last_frame_ts

    def _run(self) -> None:
        cap = None
        retry_seconds = _local_camera_retry_seconds()
        interval = 1.0 / _processed_stream_fps()
        source_desc = str(self.source_raw).strip()
        is_http_source = source_desc.startswith(("http://", "https://"))
        fail_count = 0

        while not self._stop_event.is_set():
            jpeg = None
            try:
                if cap is None or not cap.isOpened():
                    cap = _open_camera_capture(self.source_raw)
                    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        if cap is not None:
                            cap.release()
                            cap = None

                        if is_http_source:
                            try:
                                raw = _fetch_single_jpeg(source_desc, timeout_seconds=max(2.0, retry_seconds + 1.0))
                                if raw:
                                    jpeg = _annotate_face_jpeg(raw)
                            except Exception:
                                jpeg = None

                        if not jpeg:
                            fail_count += 1
                            if fail_count == 1 or fail_count % 20 == 0:
                                app.logger.warning(
                                    "Processed camera '%s' unavailable at source '%s' (fail=%s).",
                                    self.which,
                                    self.source_raw,
                                    fail_count,
                                )
                            time.sleep(retry_seconds)
                            continue

                if jpeg is None:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        fail_count += 1
                        if fail_count == 1 or fail_count % 20 == 0:
                            app.logger.warning(
                                "Processed camera '%s' read stalled at source '%s' (fail=%s).",
                                self.which,
                                self.source_raw,
                                fail_count,
                            )
                        if cap is not None:
                            cap.release()
                            cap = None
                        time.sleep(min(1.5, retry_seconds))
                        continue

                    jpeg = _encode_annotated_frame(frame)
                    if not jpeg:
                        time.sleep(interval * 0.5)
                        continue

                fail_count = 0
                with self._lock:
                    self._latest_jpeg = jpeg
                    self._last_frame_ts = time.time()
            except Exception:
                fail_count += 1
                if cap is not None:
                    cap.release()
                    cap = None
                if fail_count == 1 or fail_count % 20 == 0:
                    app.logger.exception("Processed camera '%s' crashed; retrying.", self.which)
                time.sleep(retry_seconds)
                continue

            time.sleep(interval)

        if cap is not None:
            cap.release()


def _get_processed_camera_worker(which: str) -> Optional[_ProcessedCameraWorker]:
    source_raw = _camera_capture_source_for(which)
    if not source_raw:
        return None
    with _PROCESSED_CAMERA_WORKERS_LOCK:
        prev_source = _PROCESSED_CAMERA_BINDINGS.get(which)
        if prev_source and prev_source != source_raw:
            _PROCESSED_CAMERA_BINDINGS.pop(which, None)
            old_worker = _PROCESSED_CAMERA_WORKERS.get(prev_source)
            if old_worker and prev_source not in _PROCESSED_CAMERA_BINDINGS.values():
                old_worker.stop()
                _PROCESSED_CAMERA_WORKERS.pop(prev_source, None)

        worker = _PROCESSED_CAMERA_WORKERS.get(source_raw)
        if worker is None:
            worker = _ProcessedCameraWorker(which=which, source_raw=source_raw)
            worker.start()
            _PROCESSED_CAMERA_WORKERS[source_raw] = worker
        _PROCESSED_CAMERA_BINDINGS[which] = source_raw
        return worker


def _stop_local_camera_workers() -> None:
    with _LOCAL_CAMERA_WORKERS_LOCK:
        workers = list(_LOCAL_CAMERA_WORKERS.values())
        _LOCAL_CAMERA_WORKERS.clear()
        _LOCAL_CAMERA_BINDINGS.clear()
    for worker in workers:
        worker.stop()


def _stop_processed_camera_workers() -> None:
    with _PROCESSED_CAMERA_WORKERS_LOCK:
        workers = list(_PROCESSED_CAMERA_WORKERS.values())
        _PROCESSED_CAMERA_WORKERS.clear()
        _PROCESSED_CAMERA_BINDINGS.clear()
    for worker in workers:
        worker.stop()


atexit.register(_stop_local_camera_workers)
atexit.register(_stop_processed_camera_workers)

@app.get("/camera/<string:which>")
def camera_proxy(which: str):
    src_url = _camera_url_for(which)
    if not src_url:
        abort(404)

    def stream_from_source():
        # Keep the proxy alive so Tailscale clients do not need LAN access to ESP32 directly.
        while True:
            try:
                req = urllib_request.Request(src_url, headers={"User-Agent": "CondoCameraProxy/1.0"})
                with urllib_request.urlopen(req, timeout=10) as upstream:
                    while True:
                        chunk = upstream.read(8192)
                        if not chunk:
                            break
                        yield chunk
            except Exception:
                time.sleep(0.8)

    resp = Response(stream_from_source(), mimetype="multipart/x-mixed-replace; boundary=frame")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.get("/camera/frame/<string:which>")
def camera_frame(which: str):
    src_url = _camera_url_for(which)
    if not src_url:
        abort(404)
    try:
        jpeg = _fetch_single_jpeg(src_url)
    except Exception:
        jpeg = None
    if not jpeg:
        return Response("camera unavailable", status=503, mimetype="text/plain")
    jpeg = _annotate_face_jpeg(jpeg)
    resp = Response(jpeg, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/camera/processed/frame/<string:which>")
def camera_processed_frame(which: str):
    if which not in ("outdoor", "indoor"):
        abort(404)
    worker = _get_processed_camera_worker(which)
    if not worker:
        abort(404)
    jpeg = worker.latest_frame()

    if not jpeg:
        return Response("camera unavailable", status=503, mimetype="text/plain")
    resp = Response(jpeg, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/camera/processed/stream/<string:which>")
def camera_processed_stream(which: str):
    if which not in ("outdoor", "indoor"):
        abort(404)
    worker = _get_processed_camera_worker(which)
    if not worker:
        abort(404)
    fps = _processed_stream_fps()
    interval = 1.0 / fps

    def generate():
        last_sent_ts = 0.0
        while True:
            jpeg, ts_value = worker.latest_frame_with_ts()
            if not jpeg:
                time.sleep(interval)
                continue
            if ts_value <= last_sent_ts:
                time.sleep(interval * 0.5)
                continue
            last_sent_ts = ts_value
            header = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
            )
            yield header + jpeg + b"\r\n"
            time.sleep(interval)

    resp = Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/camera/local/frame/<string:which>")
def camera_local_frame(which: str):
    if which not in ("outdoor", "indoor"):
        abort(404)
    worker = _get_local_camera_worker(which)
    if not worker:
        abort(404)
    jpeg = worker.latest_frame()
    if not jpeg:
        return Response("camera unavailable", status=503, mimetype="text/plain")
    jpeg = _annotate_face_jpeg(jpeg)
    resp = Response(jpeg, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/camera/local/stream/<string:which>")
def camera_local_stream(which: str):
    if which not in ("outdoor", "indoor"):
        abort(404)
    worker = _get_local_camera_worker(which)
    if not worker:
        abort(404)

    fps = _local_stream_fps()
    interval = 1.0 / fps

    def generate():
        last_sent_ts = 0.0
        while True:
            jpeg, ts_value = worker.latest_frame_with_ts()
            if not jpeg:
                time.sleep(interval)
                continue
            if ts_value <= last_sent_ts:
                time.sleep(interval * 0.5)
                continue
            last_sent_ts = ts_value
            jpeg = _annotate_face_jpeg(jpeg)
            header = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
            )
            yield header + jpeg + b"\r\n"
            time.sleep(interval)

    resp = Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

# ---- Dashboard / Alerts ----
@app.get("/dashboard")
@app.get("/dashboard/<path:spa_path>")
def dashboard(spa_path: str = ""):
    if _react_dashboard_ready():
        return _serve_react_dashboard(spa_path)
    if spa_path:
        return redirect(url_for("dashboard"))
    return _render_dashboard_template()


@app.get("/dashboard-legacy")
def dashboard_legacy():
    return _render_dashboard_template()


@app.get("/api/dashboard/live")
def dashboard_live():
    alerts = list_active_alerts(limit=12)
    recent_events = list_recent_events(limit=10)
    counts = _dashboard_node_counts()
    return jsonify(
        {
            "active_alert_count": count_active_alerts(),
            "sensors_online": counts["sensors_online"],
            "sensors_total": counts["sensors_total"],
            "cameras_online": counts["cameras_online"],
            "cameras_total": counts["cameras_total"],
            "alerts": [_serialize_alert_row(row) for row in alerts],
            "recent_events": [_serialize_event_row(row) for row in recent_events],
        }
    )


@app.get("/api/ui/events/live")
def ui_events_live():
    try:
        limit = int(request.args.get("limit", "250"))
    except Exception:
        limit = 250
    limit = max(20, min(limit, 500))
    event_rows = list_recent_events(limit=limit)
    alert_rows = list_active_alerts(limit=limit)
    return jsonify(
        {
            "ok": True,
            "events": [_ui_event_from_event_row(row) for row in event_rows],
            "alerts": [_ui_alert_from_alert_row(row) for row in alert_rows],
        }
    )


@app.post("/api/ui/camera/control")
def ui_camera_control():
    payload = request.get_json(silent=True) or {}
    node_id = normalize_node_id(payload.get("node_id", ""))
    command = str(payload.get("command", "")).strip().lower()
    allowed_commands = {"flash_on", "flash_off", "status"}

    meta = NODE_META.get(node_id) or {}
    if meta.get("kind") != "camera":
        return jsonify({"ok": False, "error": "Invalid camera node.", "node_id": node_id}), 400

    if command not in allowed_commands:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Unsupported camera command.",
                    "allowed_commands": sorted(allowed_commands),
                }
            ),
            400,
        )

    ok, err, topic = _publish_camera_control(node_id, command)
    if not ok:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": f"Failed to publish camera command: {err}",
                    "node_id": node_id,
                    "command": command,
                    "topic": topic,
                }
            ),
            502,
        )

    return jsonify({"ok": True, "node_id": node_id, "command": command, "topic": topic})


@app.get("/api/ui/nodes/live")
def ui_nodes_live():
    node_rows = list_node_status()
    node_map = {str(row["node"]): row for row in node_rows}

    sensors: list[dict] = []
    camera_feeds: list[dict] = []

    for node_id, meta in NODE_META.items():
        row = node_map.get(node_id)
        last_seen = str(row["last_seen_ts"] if row else "")
        online = _is_online(last_seen)
        note = str(row["note"] if row and row["note"] else "")
        role = str(meta.get("role", ""))
        node_type = "force" if role == "door_force" else ("camera" if meta.get("kind") == "camera" else "smoke")
        status = "online" if online else "offline"
        if online and note and any(token in note.lower() for token in ("warn", "retry", "unstable", "high")):
            status = "warning"

        sensors.append(
            {
                "id": node_id,
                "name": str(meta.get("label", node_id)),
                "location": str(meta.get("room", "")),
                "type": node_type,
                "status": status,
                "last_update": last_seen or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": note or ("Recent heartbeat received." if online else "No recent heartbeat."),
            }
        )

        if meta.get("kind") == "camera":
            which = "outdoor" if node_id == "cam_outdoor" else "indoor"
            stream_path = ""
            source_raw = _camera_capture_source_for(which)
            if source_raw:
                # Use backend processed stream to overlay live face boxes/labels.
                stream_path = f"/camera/processed/stream/{which}"

            camera_feeds.append(
                {
                    "location": str(meta.get("room", "")),
                    "node_id": node_id,
                    "status": "online" if online else "offline",
                    "quality": "ESP32-CAM + OpenCV overlay",
                    "fps": 20 if online else 0,
                    "latency_ms": 150 if online else 0,
                    "stream_path": stream_path,
                    "stream_available": bool(stream_path),
                }
            )

    latest_event = list_recent_events(limit=1)
    latest_event_ts = str(latest_event[0]["ts"]) if latest_event else ""
    ingest_status = "online" if _is_online(latest_event_ts) else "warning"
    online_nodes = len([node for node in sensors if node["status"] == "online"])
    mqtt_status = "connected" if online_nodes > 0 else "disconnected"

    services = [
        {
            "id": "service-001",
            "name": "Mosquitto Broker",
            "status": "online" if mqtt_status == "connected" else "warning",
            "endpoint": f"mqtt://{os.environ.get('MQTT_BROKER_HOST', '127.0.0.1').strip()}:{int(os.environ.get('MQTT_BROKER_PORT', '1883'))}",
            "last_update": latest_event_ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "detail": f"Topic root: {os.environ.get('MQTT_TOPIC_ROOT', 'thesis/v1').strip() or 'thesis/v1'}",
        },
        {
            "id": "service-002",
            "name": "MQTT Ingest Service",
            "status": ingest_status,
            "endpoint": "pi/mqtt_ingest.py",
            "last_update": latest_event_ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "detail": "Forwarding sensor payloads to POST /api/sensors/event",
        },
        {
            "id": "service-003",
            "name": "Flask API + Dashboard",
            "status": "online",
            "endpoint": "pi/app.py",
            "last_update": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "detail": "Core API, fusion logic, and UI endpoints active",
        },
    ]

    vision_event = get_latest_event("VISION_HEARTBEAT")
    vision_last = str(vision_event["ts"]) if vision_event else ""
    vision_status = "online" if _is_online(vision_last) else "warning"
    services.append(
        {
            "id": "service-004",
            "name": "Vision Runtime",
            "status": vision_status,
            "endpoint": "pi/vision_runtime.py",
            "last_update": vision_last or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "detail": "OpenCV face/flame pipeline heartbeat",
        }
    )

    detection_pipelines = [
        {
            "name": "Face Recognition (OpenCV LBPH)",
            "state": "active" if vision_status == "online" else "degraded",
            "detail": "Authorized vs unknown classification",
        },
        {
            "name": "Visual Flame Detection",
            "state": "active" if vision_status == "online" else "degraded",
            "detail": "Indoor flame signal inference",
        },
        {
            "name": "Smoke Sensor Ingest (MQ-2)",
            "state": "active" if len([n for n in sensors if n["type"] == "smoke" and n["status"] == "online"]) > 0 else "degraded",
            "detail": "MQTT sensor payload monitoring",
        },
        {
            "name": "Door-Force Event Monitor",
            "state": "active" if any(n["id"] == "door_force" and n["status"] == "online" for n in sensors) else "degraded",
            "detail": "Door impact threshold trigger monitor",
        },
    ]

    return jsonify(
        {
            "ok": True,
            "sensor_statuses": sensors,
            "service_statuses": services,
            "camera_feeds": camera_feeds,
            "detection_pipelines": detection_pipelines,
            "system_health": {
                "raspberryPi": "online",
                "mqtt": mqtt_status,
                "ingest": "online" if ingest_status == "online" else "offline",
                "last_sync": latest_event_ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "uptime": _runtime_uptime_label(),
            },
        }
    )


@app.get("/api/ui/stats/daily")
def ui_stats_daily():
    try:
        days = int(request.args.get("days", "7"))
    except Exception:
        days = 7
    days = max(1, min(days, 31))

    today = datetime.now(timezone.utc).date()
    series = []
    for offset in range(days - 1, -1, -1):
        date_str = (today - timedelta(days=offset)).isoformat()
        summary = summary_for_date(date_str)
        events = {str(item["type"]): int(item["c"]) for item in summary.get("events_by_type", [])}
        alerts = {}
        for item in summary.get("alerts_by_type_status", []):
            alert_key = str(item.get("type", ""))
            alerts[alert_key] = alerts.get(alert_key, 0) + int(item.get("c", 0))

        series.append(
            {
                "date": date_str,
                "authorized_faces": events.get("AUTHORIZED", 0),
                "unknown_detections": events.get("UNKNOWN", 0),
                "flame_signals": events.get("FLAME_SIGNAL", 0),
                "smoke_high_events": events.get("SMOKE_HIGH", 0),
                "fire_alerts": alerts.get("FIRE", 0),
                "intruder_alerts": alerts.get("INTRUDER", 0),
                "avg_response_seconds": 0.0,
            }
        )

    return jsonify({"ok": True, "days": days, "stats": series})


@app.get("/api/ui/settings/live")
def ui_settings_live():
    profiles = [_ui_profile_from_face_row(row) for row in list_faces()]

    runtime_settings = [
        {
            "key": "SENSOR_EVENT_URL",
            "value": os.environ.get("SENSOR_EVENT_URL", "http://127.0.0.1:5000/api/sensors/event"),
            "description": "Sensor event API endpoint",
        },
        {
            "key": "MQTT_TOPIC_ROOT",
            "value": os.environ.get("MQTT_TOPIC_ROOT", "thesis/v1"),
            "description": "MQTT publish/subscribe root topic",
        },
        {
            "key": "FIRE_FUSION_WINDOW",
            "value": f"{os.environ.get('FIRE_FUSION_WINDOW', '120')} seconds",
            "description": "Smoke + flame correlation window",
        },
        {
            "key": "INTRUDER_FUSION_WINDOW",
            "value": f"{os.environ.get('INTRUDER_FUSION_WINDOW', '120')} seconds",
            "description": "Unknown + door evidence correlation window",
        },
        {
            "key": "ALERT_COOLDOWN",
            "value": f"{os.environ.get('ALERT_COOLDOWN', '45')} seconds",
            "description": "Intruder alert cooldown interval",
        },
        {
            "key": "FIRE_COOLDOWN",
            "value": f"{os.environ.get('FIRE_COOLDOWN', '75')} seconds",
            "description": "Fire alert cooldown interval",
        },
    ]

    return jsonify(
        {
            "ok": True,
            "guest_mode": get_guest_mode(),
            "authorized_profiles": profiles,
            "runtime_settings": runtime_settings,
        }
    )


@app.get("/api/faces")
def api_faces_list():
    profiles = [_ui_profile_from_face_row(row) for row in list_faces()]
    return jsonify({"ok": True, "faces": profiles})


@app.post("/api/faces")
def api_faces_create():
    payload = request.get_json(silent=True) or {}
    name = _safe_name(payload.get("name", ""))
    note = str(payload.get("note", "")).strip()
    if not name:
        return jsonify({"ok": False, "error": "Name is required."}), 400

    existing_id = None
    for row in list_faces():
        row_name = str(row["name"] or "").strip().lower()
        if row_name == name.lower():
            existing_id = int(row["id"])
            break

    face_id = existing_id if existing_id is not None else create_face(name=name, is_authorized=True, note=note)
    face_row = get_face(face_id)
    if not face_row:
        return jsonify({"ok": False, "error": "Failed to load face profile."}), 500

    return jsonify(
        {
            "ok": True,
            "created": existing_id is None,
            "face": _ui_profile_from_face_row(face_row),
        }
    )


@app.delete("/api/faces/<int:face_id>")
def api_faces_delete(face_id: int):
    ok = delete_face(face_id)
    if not ok:
        return jsonify({"ok": False, "error": "Face not found.", "face_id": face_id}), 404
    return jsonify({"ok": True, "face_id": face_id})


@app.get("/api/training/face/status")
def api_training_face_status():
    return training_face_status()


@app.post("/api/training/face/capture")
def api_training_face_capture():
    return training_face_capture()


@app.post("/api/training/face/train")
def api_training_face_train():
    ok, msg = _run_face_training()
    response = {
        "ok": ok,
        "message": msg[:4000],
        "model_path": LBPH_MODEL_PATH if ok else "",
    }
    return jsonify(response), (200 if ok else 500)


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
        flash(f"Alert #{alert_id} set to {_friendly_status_label(status)}.", "success")
    else:
        flash(f"Alert #{alert_id} was not active, so nothing changed.", "warning")
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
    api_key_required = os.environ.get("SENSOR_API_KEY", "").strip()
    if api_key_required:
        req_key = request.headers.get("X-API-KEY", "").strip()
        if req_key != api_key_required:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

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
    event_source = node_id
    if node_id == "cam_outdoor":
        event_source = "CAM_OUTDOOR"
    elif node_id == "cam_indoor":
        event_source = "CAM_INDOOR"

    create_event(event, source=event_source, details=details, ts=ts_iso, room=room)
    update_node_seen(node_id, note=details or event, ts=ts_iso)
    alert_id = None
    if event == EVENT_SMOKE_HIGH:
        alert_id = handle_fire_signal(ts_iso, room=room)
    elif event == EVENT_FLAME_SIGNAL:
        alert_id = handle_fire_signal(ts_iso, room=room)
    elif event == EVENT_DOOR_FORCE:
        alert_id = handle_door_force_signal(ts_iso, room=room)
    elif event == EVENT_UNKNOWN:
        alert_id = handle_intruder_evidence(ts_iso, room=room)
    elif event == "DOOR_SENSOR_OFFLINE":
        cooldown = int(os.environ.get("DOOR_OFFLINE_ALERT_COOLDOWN_SECONDS", "300"))
        if not has_recent_alert("DOOR_SENSOR_OFFLINE", within_seconds=cooldown, ts=ts_iso, room=room):
            alert_id = create_alert(
                "DOOR_SENSOR_OFFLINE",
                room=room,
                severity=2,
                status="ACTIVE",
                details=details or "door_force reported offline (MQTT LWT/status).",
                ts=ts_iso,
            )

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
            "target_reached": count >= FACE_TARGET_SAMPLES,
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

    face_roi, faces_detected, best_rect = _extract_training_face(frame)
    validation_error = _validate_face_roi(face_roi)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error}), 422
    result = _save_face_sample(name, face_roi)
    result["faces_detected"] = int(faces_detected)
    if best_rect:
        x, y, w, h = best_rect
        result["face_box"] = {"x": x, "y": y, "w": w, "h": h}
    return jsonify(result)


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

    face_roi, faces_detected, best_rect = _extract_training_face(frame)
    validation_error = _validate_face_roi(face_roi)
    if validation_error:
        return jsonify({"ok": False, "error": validation_error}), 422
    result = _save_face_sample(name, face_roi)
    result["faces_detected"] = int(faces_detected)
    if best_rect:
        x, y, w, h = best_rect
        result["face_box"] = {"x": x, "y": y, "w": w, "h": h}
    return jsonify(result)


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

@app.post("/settings/telegram/test")
def telegram_test():
    ok, error = send_telegram_test_message()
    if ok:
        flash("Telegram test message sent.", "success")
    else:
        flash("Telegram test failed. Check TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID and internet.\n" + error, "warning")
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
