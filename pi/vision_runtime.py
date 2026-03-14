import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

import cv2

from config import (
    EVENT_AUTHORIZED,
    EVENT_FLAME_SIGNAL,
    EVENT_UNKNOWN,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PASSWORD,
    MQTT_BROKER_PORT,
    MQTT_BROKER_USERNAME,
    MQTT_TOPIC_ROOT,
)
from db import create_event, create_snapshot, init_db, update_node_seen
from fire_utils import detect_flame_signal, load_fire_model
from fusion import handle_fire_signal, handle_intruder_evidence
from vision_utils import analyze_faces, draw_face_detections, save_frame_snapshot

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "lbph.yml")
LABELS_PATH = os.path.join(MODELS_DIR, "labels.json")
FIRE_MODEL_PATH = os.path.join(MODELS_DIR, "fire_color.json")


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
                    line = line[len("export ") :].strip()
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


def _iso_utc(ts: Optional[str] = None) -> str:
    if ts:
        return ts
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def _lbph_version():
    if not (os.path.exists(MODEL_PATH) and os.path.exists(LABELS_PATH)):
        return None
    return (os.path.getmtime(MODEL_PATH), os.path.getmtime(LABELS_PATH))


def _face_event_details(detections):
    if not detections:
        return "faces=0"
    known = [d["label"] for d in detections if d.get("label") and d["label"] != "UNKNOWN"]
    unknown_count = len([d for d in detections if d.get("label") == "UNKNOWN"])
    parts = [f"faces={len(detections)}", f"unknown={unknown_count}"]
    if known:
        parts.append("known=" + ",".join(known[:3]))
    confs = [f"{float(d.get('confidence', 999.0)):.1f}" for d in detections[:3]]
    if confs:
        parts.append("conf=" + ",".join(confs))
    return " | ".join(parts)


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


def _sources_match(a, b) -> bool:
    if _is_empty(a) or _is_empty(b):
        return False
    return _coerce_capture_source(a) == _coerce_capture_source(b)


def _source_for_node(node_id: str) -> str:
    if node_id == "cam_outdoor":
        return "CAM_OUTDOOR"
    if node_id == "cam_indoor":
        return "CAM_INDOOR"
    return node_id


def _post_event_api(payload: dict, api_url: str, api_key: str, timeout: float = 4.0) -> tuple[bool, str]:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key
    req = urllib.request.Request(api_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return 200 <= resp.status < 300, f"code={resp.status} body={body[:140]}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        return False, f"http_error={exc.code} body={body[:140]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"error={exc}"


class VisionEventEmitter:
    def __init__(self, args):
        self.mode = args.event_sink
        self.api_url = args.api_url
        self.api_key = args.api_key
        self.api_timeout = args.api_timeout
        self.status_interval = max(5.0, float(args.status_heartbeat_seconds))
        self._last_status_by_node: dict[str, float] = {}

        self._mqtt_client = None
        self._mqtt_qos = int(args.mqtt_qos)
        self._mqtt_topic_root = args.mqtt_topic_root.strip().strip("/")
        self._seq = 0

        if self.mode == "mqtt":
            if mqtt is None:
                raise SystemExit("paho-mqtt is not installed. Install paho-mqtt or use --event-sink api/db.")
            client_id = args.mqtt_client_id.strip() or "vision-runtime"
            client = mqtt.Client(client_id=client_id, clean_session=True)
            if args.mqtt_username:
                client.username_pw_set(args.mqtt_username, args.mqtt_password)
            client.reconnect_delay_set(min_delay=1, max_delay=20)
            try:
                client.connect(args.mqtt_host, args.mqtt_port, keepalive=45)
            except Exception as exc:  # noqa: BLE001
                raise SystemExit(f"Cannot connect to MQTT broker {args.mqtt_host}:{args.mqtt_port}: {exc}") from exc
            client.loop_start()
            self._mqtt_client = client

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _publish_mqtt(self, topic: str, payload: dict, retain: bool = False) -> bool:
        if self._mqtt_client is None:
            return False
        try:
            info = self._mqtt_client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=self._mqtt_qos, retain=retain)
            info.wait_for_publish(timeout=2.0)
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception:
            return False

    def emit_status(self, node_id: str, note: str = "", ts: Optional[str] = None) -> None:
        now = time.time()
        last = self._last_status_by_node.get(node_id, 0.0)
        if (now - last) < self.status_interval:
            return
        self._last_status_by_node[node_id] = now
        ts_iso = _iso_utc(ts)

        if self.mode == "db":
            update_node_seen(node_id, note=note or "vision loop", ts=ts_iso)
            return

        if self.mode == "api":
            payload = {
                "node": node_id,
                "event": "CAM_HEARTBEAT" if node_id.startswith("cam_") else "VISION_HEARTBEAT",
                "note": note or "vision heartbeat",
                "ts": ts_iso,
            }
            ok, detail = _post_event_api(payload, self.api_url, self.api_key, self.api_timeout)
            if not ok:
                print(f"[vision] status API post failed for {node_id}: {detail}")
            return

        payload = {"v": 1, "s": 1, "q": self._next_seq(), "t": int(datetime.now(timezone.utc).timestamp())}
        if note:
            payload["m"] = note
        topic = f"{self._mqtt_topic_root}/status/{node_id}"
        if not self._publish_mqtt(topic, payload, retain=True):
            print(f"[vision] mqtt status publish failed topic={topic}")

    def emit_event(
        self,
        node_id: str,
        event_name: str,
        room: str,
        details: str,
        ts: Optional[str] = None,
        value: Optional[float] = None,
        unit: str = "",
    ) -> None:
        ts_iso = _iso_utc(ts)
        event_name = str(event_name or "").strip().upper()
        if not event_name:
            return

        if self.mode == "db":
            source = _source_for_node(node_id)
            create_event(event_name, source, details=details or "", ts=ts_iso, room=room)
            update_node_seen(node_id, note=details or event_name, ts=ts_iso)
            if event_name == EVENT_UNKNOWN:
                alert_id = handle_intruder_evidence(ts_iso)
                if alert_id:
                    print(f"🚨 INTRUDER alert #{alert_id} created (fusion).")
            elif event_name == EVENT_FLAME_SIGNAL:
                alert_id = handle_fire_signal(ts_iso)
                if alert_id:
                    print(f"🔥 FIRE alert #{alert_id} created (fusion).")
            return

        if self.mode == "api":
            payload = {"node": node_id, "event": event_name, "room": room, "note": details or "", "ts": ts_iso}
            if value is not None:
                payload["value"] = value
            if unit:
                payload["unit"] = unit
            ok, detail = _post_event_api(payload, self.api_url, self.api_key, self.api_timeout)
            if not ok:
                print(f"[vision] API post failed node={node_id} event={event_name}: {detail}")
            return

        payload = {"v": 1, "e": event_name, "q": self._next_seq(), "t": int(datetime.now(timezone.utc).timestamp())}
        if details:
            payload["m"] = details
        if value is not None:
            payload["x"] = round(float(value), 6)
        if unit:
            payload["u"] = unit
        if room:
            payload["room"] = room
        topic = f"{self._mqtt_topic_root}/events/{node_id}"
        if not self._publish_mqtt(topic, payload, retain=False):
            print(f"[vision] mqtt publish failed topic={topic} event={event_name}")

    def close(self) -> None:
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="OpenCV runtime to generate face/flame events.")
    parser.add_argument(
        "--camera-mode",
        default=os.environ.get("CAMERA_MODE", "auto"),
        type=str.lower,
        choices=["auto", "webcam", "esp32"],
        help="Camera source preset: auto uses env/default, webcam uses local camera, esp32 expects URLs",
    )
    parser.add_argument(
        "--outdoor-url",
        default=os.environ.get("OUTDOOR_URL"),
        help="Outdoor stream URL or webcam index (env OUTDOOR_URL). Example: 0 or http://<ip>:81/stream",
    )
    parser.add_argument(
        "--indoor-url",
        default=os.environ.get("INDOOR_URL"),
        help="Indoor stream URL or webcam index (env INDOOR_URL). Optional.",
    )
    parser.add_argument("--process-every", type=int, default=int(os.environ.get("PROCESS_EVERY", "5")))
    parser.add_argument("--unknown-streak", type=int, default=int(os.environ.get("UNKNOWN_STREAK", "12")))
    parser.add_argument("--unknown-threshold", type=float, default=float(os.environ.get("UNKNOWN_THRESHOLD", "65")))
    parser.add_argument("--cooldown-seconds", type=int, default=int(os.environ.get("ALERT_COOLDOWN", "45")))
    parser.add_argument("--flame-streak", type=int, default=int(os.environ.get("FLAME_STREAK", "8")))
    parser.add_argument("--fire-cooldown-seconds", type=int, default=int(os.environ.get("FIRE_COOLDOWN", "75")))
    parser.add_argument("--fire-ratio-threshold", type=float, default=float(os.environ.get("FIRE_RATIO_THRESHOLD", "0")))
    parser.add_argument("--fire-min-blob-ratio", type=float, default=float(os.environ.get("FIRE_MIN_BLOB_RATIO", "0.0015")))
    parser.add_argument("--fire-min-hot-ratio", type=float, default=float(os.environ.get("FIRE_MIN_HOT_RATIO", "0.0008")))

    parser.add_argument(
        "--event-sink",
        default=os.environ.get("VISION_EVENT_SINK", "mqtt").strip().lower(),
        choices=["mqtt", "api", "db"],
        help="Where vision events go: mqtt (recommended), api, or db (legacy local mode).",
    )
    parser.add_argument(
        "--status-heartbeat-seconds",
        type=float,
        default=float(os.environ.get("VISION_STATUS_HEARTBEAT_SECONDS", "15")),
    )
    parser.add_argument("--api-url", default=os.environ.get("SENSOR_EVENT_URL", "http://127.0.0.1:5000/api/sensors/event"))
    parser.add_argument("--api-key", default=os.environ.get("SENSOR_API_KEY", ""))
    parser.add_argument("--api-timeout", type=float, default=float(os.environ.get("VISION_API_TIMEOUT", "4.0")))
    parser.add_argument("--mqtt-host", default=os.environ.get("MQTT_BROKER_HOST", MQTT_BROKER_HOST))
    parser.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_BROKER_PORT", str(MQTT_BROKER_PORT))))
    parser.add_argument("--mqtt-username", default=os.environ.get("MQTT_BROKER_USERNAME", MQTT_BROKER_USERNAME))
    parser.add_argument("--mqtt-password", default=os.environ.get("MQTT_BROKER_PASSWORD", MQTT_BROKER_PASSWORD))
    parser.add_argument("--mqtt-client-id", default=os.environ.get("VISION_MQTT_CLIENT_ID", "vision-runtime"))
    parser.add_argument("--mqtt-topic-root", default=os.environ.get("MQTT_TOPIC_ROOT", MQTT_TOPIC_ROOT))
    parser.add_argument("--mqtt-qos", type=int, default=int(os.environ.get("VISION_MQTT_QOS", "1")))

    args = parser.parse_args()

    init_db()
    emitter = VisionEventEmitter(args)

    outdoor_src, indoor_src = _resolve_sources(args)

    outdoor = cv2.VideoCapture(_coerce_capture_source(outdoor_src))
    if not outdoor.isOpened():
        raise SystemExit(f"❌ Cannot open outdoor stream: {outdoor_src}")

    indoor = None
    reuse_outdoor_for_indoor = False
    if not _is_empty(indoor_src):
        if _sources_match(outdoor_src, indoor_src):
            indoor = outdoor
            reuse_outdoor_for_indoor = True
            print("ℹ️  Indoor source matches outdoor source. Reusing one camera capture for both feeds.")
        else:
            indoor = cv2.VideoCapture(_coerce_capture_source(indoor_src))
            if not indoor.isOpened():
                print(f"⚠️  Cannot open indoor stream: {indoor_src} (continuing with outdoor only)")
                indoor = None

    recognizer, id_to_name = load_lbph()
    model_version = _lbph_version()
    fire_model = load_fire_model(FIRE_MODEL_PATH)
    fire_model_mtime = os.path.getmtime(FIRE_MODEL_PATH) if os.path.exists(FIRE_MODEL_PATH) else 0
    fire_threshold = args.fire_ratio_threshold if args.fire_ratio_threshold > 0 else (float(fire_model["ratio_threshold"]) if fire_model else 0.0)

    unknown_streak_outdoor = 0
    unknown_streak_indoor = 0
    flame_streak = 0
    frame_i = 0

    print("✅ Vision runtime started")
    print(f"Mode: {args.camera_mode} | Sink: {args.event_sink} | Outdoor: {outdoor_src} | Indoor: {indoor_src or '(none)'}")
    if recognizer is None:
        print("ℹ️  No LBPH model loaded (train later). All faces are UNKNOWN until training.")
    if fire_threshold > 0:
        print(
            "ℹ️  Fire detection "
            f"threshold={fire_threshold:.4f} | min_blob={args.fire_min_blob_ratio:.4f} | min_hot={args.fire_min_hot_ratio:.4f}"
        )
    else:
        print("ℹ️  Fire model not loaded. Indoor flame detection is disabled until fire training.")

    try:
        while True:
            ok, frame = outdoor.read()
            if not ok or frame is None:
                time.sleep(0.2)
                continue

            frame_i += 1
            if frame_i % args.process_every != 0:
                continue

            current_model_version = _lbph_version()
            if current_model_version != model_version:
                recognizer, id_to_name = load_lbph()
                model_version = current_model_version
                print("🔄 Reloaded LBPH model after retrain.")

            if os.path.exists(FIRE_MODEL_PATH):
                fm = os.path.getmtime(FIRE_MODEL_PATH)
                if fm != fire_model_mtime:
                    fire_model = load_fire_model(FIRE_MODEL_PATH)
                    fire_model_mtime = fm
                    fire_threshold = args.fire_ratio_threshold if args.fire_ratio_threshold > 0 else (float(fire_model["ratio_threshold"]) if fire_model else 0.0)
                    print(f"🔄 Reloaded fire model (threshold={fire_threshold:.4f}).")

            ts = _iso_utc()
            emitter.emit_status("cam_outdoor", note="opencv loop", ts=ts)

            detections = analyze_faces(frame, recognizer=recognizer, id_to_name=id_to_name, unknown_threshold=args.unknown_threshold)
            if len(detections) == 0:
                unknown_streak_outdoor = max(0, unknown_streak_outdoor - 1)
            else:
                unknown_faces = [d for d in detections if d.get("label") == "UNKNOWN"]
                if unknown_faces:
                    unknown_streak_outdoor += 1
                    primary_unknown = max(unknown_faces, key=lambda d: float(d.get("confidence", 999.0)))
                    conf = float(primary_unknown.get("confidence", 999.0))
                    details = _face_event_details(detections)
                    emitter.emit_event("cam_outdoor", EVENT_UNKNOWN, "Door Entrance Area", details, ts=ts)

                    if unknown_streak_outdoor in (1, 6, args.unknown_streak):
                        overlay = draw_face_detections(frame, detections)
                        rel, _ = save_frame_snapshot(
                            overlay if overlay is not None else frame,
                            prefix=f"outdoor_unknown_{unknown_streak_outdoor}",
                            ts_iso=ts,
                        )
                        create_snapshot("FACE_UNKNOWN", "UNKNOWN", rel, linked_alert_id=None, note=f"{details} | conf={conf:.1f}", ts=ts)
                else:
                    unknown_streak_outdoor = 0
                    emitter.emit_event("cam_outdoor", EVENT_AUTHORIZED, "Door Entrance Area", _face_event_details(detections), ts=ts)

            if indoor is not None and (frame_i % (args.process_every * 6) == 0):
                if reuse_outdoor_for_indoor:
                    ok2, frame2 = True, frame
                else:
                    ok2, frame2 = indoor.read()
                if ok2 and frame2 is not None:
                    emitter.emit_status("cam_indoor", note="opencv loop", ts=ts)

                    detections2 = analyze_faces(
                        frame2,
                        recognizer=recognizer,
                        id_to_name=id_to_name,
                        unknown_threshold=args.unknown_threshold,
                    )
                    if len(detections2) == 0:
                        unknown_streak_indoor = max(0, unknown_streak_indoor - 1)
                    else:
                        unknown_faces2 = [d for d in detections2 if d.get("label") == "UNKNOWN"]
                        if unknown_faces2:
                            unknown_streak_indoor += 1
                            primary_unknown2 = max(unknown_faces2, key=lambda d: float(d.get("confidence", 999.0)))
                            conf2 = float(primary_unknown2.get("confidence", 999.0))
                            details2 = _face_event_details(detections2)
                            emitter.emit_event("cam_indoor", EVENT_UNKNOWN, "Living Room", details2, ts=ts)
                            if unknown_streak_indoor in (1, 4, args.unknown_streak):
                                overlay2 = draw_face_detections(frame2, detections2)
                                rel2, _ = save_frame_snapshot(
                                    overlay2 if overlay2 is not None else frame2,
                                    prefix=f"indoor_unknown_{unknown_streak_indoor}",
                                    ts_iso=ts,
                                )
                                create_snapshot("FACE_UNKNOWN", "UNKNOWN", rel2, linked_alert_id=None, note=f"{details2} | conf={conf2:.1f}", ts=ts)
                        else:
                            unknown_streak_indoor = 0
                            emitter.emit_event("cam_indoor", EVENT_AUTHORIZED, "Living Room", _face_event_details(detections2), ts=ts)

                    if fire_threshold > 0:
                        is_flame, ratio = detect_flame_signal(
                            frame2,
                            fire_threshold,
                            min_blob_ratio=args.fire_min_blob_ratio,
                            min_hot_ratio=args.fire_min_hot_ratio,
                        )
                        if is_flame:
                            flame_streak += 1
                            emitter.emit_event(
                                "cam_indoor",
                                EVENT_FLAME_SIGNAL,
                                "Living Room",
                                f"ratio={ratio:.4f}",
                                ts=ts,
                                value=ratio,
                                unit="ratio",
                            )
                            if flame_streak in (1, args.flame_streak):
                                rel, _ = save_frame_snapshot(frame2, prefix=f"indoor_flame_{flame_streak}", ts_iso=ts)
                                create_snapshot("FLAME_SIGNAL", "FLAME", rel, linked_alert_id=None, note=f"ratio={ratio:.4f}", ts=ts)
                        else:
                            flame_streak = max(0, flame_streak - 1)

            time.sleep(0.01)
    finally:
        emitter.close()


if __name__ == "__main__":
    main()
