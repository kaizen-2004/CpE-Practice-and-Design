import os
import re
import mimetypes
import json
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from db import (
    SNAPSHOT_DIR,
    list_active_alerts,
    create_alert_notification_log,
    get_last_notification_attempt,
    get_last_successful_notification,
    count_successful_notifications,
)

try:
    import cv2
except Exception:
    cv2 = None


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except Exception:
        value = default
    return max(low, min(high, value))


def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except Exception:
        value = default
    return max(low, min(high, value))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "1" if default else "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_schedule_seconds() -> List[int]:
    raw = os.environ.get("ALERT_REMINDER_SCHEDULE", "0,60,180,300")
    out: List[int] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        try:
            sec = int(p)
        except Exception:
            continue
        out.append(max(0, sec))
    if not out:
        out = [0, 60, 180, 300]
    return sorted(set(out))


def telegram_is_configured() -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return bool(token and chat_id)


def _telegram_api_url(method: str = "sendMessage") -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    return f"https://api.telegram.org/bot{token}/{method}"


def _telegram_response_ok(status: int, body: str) -> bool:
    if not (200 <= int(status) < 300):
        return False
    try:
        payload = json.loads(body or "{}")
    except Exception:
        return True
    return bool(payload.get("ok"))


def _encode_multipart(fields: dict, files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    boundary = f"----CondoBoundary{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for field_name, filename, content_type, data in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _alert_link(alert_id: int) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if not base:
        return ""
    return f"{base.rstrip('/')}/alert/{int(alert_id)}"


def _severity_label(severity: int) -> str:
    if int(severity) >= 3:
        return "HIGH"
    if int(severity) == 2:
        return "MEDIUM"
    return "LOW"


def _compose_alert_message(alert_row, is_initial: bool) -> str:
    alert_id = int(alert_row["id"])
    room = alert_row["room"] or "-"
    details = (alert_row["details"] or "").strip()
    link = _alert_link(alert_id)
    title = "New Alert" if is_initial else "Reminder: Alert Still Active"
    lines = [
        "Condo Monitoring System",
        title,
        f"Alert ID: #{alert_id}",
        f"Type: {alert_row['type']}",
        f"Area: {room}",
        f"Level: {_severity_label(alert_row['severity'])}",
        f"Status: {alert_row['status']}",
        f"Time (UTC): {alert_row['ts']}",
    ]
    if details:
        lines.append(f"Notes: {details}")
    if link:
        lines.append(f"Open Alert: {link}")
    return "\n".join(lines)


def send_telegram_message(text: str) -> Tuple[bool, str]:
    if not telegram_is_configured():
        return False, "telegram not configured"
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    timeout = _env_int("TELEGRAM_SEND_TIMEOUT", default=8, low=3, high=30)
    payload = urllib_parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib_request.Request(_telegram_api_url("sendMessage"), data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if _telegram_response_ok(resp.status, body):
                return True, ""
            return False, f"http status={resp.status} body={body[:260]}"
    except Exception as exc:
        return False, str(exc)


def _send_telegram_file(method: str, file_field: str, file_path: str, caption: str = "") -> Tuple[bool, str]:
    if not telegram_is_configured():
        return False, "telegram not configured"
    if not os.path.isfile(file_path):
        return False, f"file not found: {file_path}"

    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    timeout = _env_int("TELEGRAM_SEND_TIMEOUT", default=12, low=4, high=45)
    max_bytes = _env_int("TELEGRAM_MEDIA_MAX_BYTES", default=45_000_000, low=1_000_000, high=90_000_000)
    file_size = os.path.getsize(file_path)
    if file_size > max_bytes:
        return False, f"media too large ({file_size} bytes > {max_bytes} bytes)"

    with open(file_path, "rb") as f:
        payload = f.read()

    mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    body, content_type = _encode_multipart(
        fields={"chat_id": chat_id, "caption": caption},
        files=[(file_field, os.path.basename(file_path), mime, payload)],
    )

    req = urllib_request.Request(_telegram_api_url(method), data=body, method="POST")
    req.add_header("Content-Type", content_type)
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            if _telegram_response_ok(resp.status, resp_body):
                return True, ""
            return False, f"http status={resp.status} body={resp_body[:260]}"
    except Exception as exc:
        return False, str(exc)


def send_telegram_photo(photo_path: str, caption: str = "") -> Tuple[bool, str]:
    return _send_telegram_file("sendPhoto", "photo", photo_path, caption=caption)


def send_telegram_document(file_path: str, caption: str = "") -> Tuple[bool, str]:
    return _send_telegram_file("sendDocument", "document", file_path, caption=caption)


def send_telegram_test_message() -> Tuple[bool, str]:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip()
    text = "Condo Monitoring System\nTelegram connection test is successful."
    if base:
        text += f"\nDashboard: {base.rstrip('/')}/dashboard"
    return send_telegram_message(text)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (value or "").strip().lower())
    return cleaned.strip("_") or "x"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_capture_source(source):
    if source is None:
        return None
    if isinstance(source, int):
        return source
    raw = str(source).strip()
    if not raw:
        return None
    if raw.lower() in ("webcam", "camera", "laptop"):
        return 0
    if raw.isdigit():
        return int(raw)
    return raw


def _camera_source_for_alert(alert_row) -> tuple[str, str]:
    alert_type = str(alert_row["type"] or "").upper()
    room = str(alert_row["room"] or "").lower()

    if alert_type == "FIRE":
        which = "indoor"
    elif alert_type == "DOOR_FORCE":
        which = "outdoor"
    elif "living" in room:
        which = "indoor"
    else:
        which = "outdoor"

    if which == "outdoor":
        source = os.environ.get("OUTDOOR_URL", "").strip() or os.environ.get("OUTDOOR_CAM_SOURCE", "").strip()
    else:
        source = os.environ.get("INDOOR_URL", "").strip() or os.environ.get("INDOOR_CAM_SOURCE", "").strip()
    return which, source


def _alert_snapshot_abs_path(alert_row) -> Optional[str]:
    raw_path = str(alert_row["snapshot_path"] or "").strip()
    if not raw_path:
        return None

    rel = raw_path
    if raw_path.startswith("snapshots/"):
        rel = raw_path[len("snapshots/") :]
    rel = rel.lstrip("/").replace("\\", "/")
    abs_path = os.path.join(SNAPSHOT_DIR, rel)
    return abs_path if os.path.isfile(abs_path) else None


def _capture_alert_snapshot_fallback(alert_row) -> Optional[str]:
    if cv2 is None:
        return None
    if not _env_bool("TELEGRAM_MEDIA_CAPTURE_FALLBACK", True):
        return None

    which, source_raw = _camera_source_for_alert(alert_row)
    source = _coerce_capture_source(source_raw)
    if source is None:
        return None

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        cap.release()
        return None

    frame = None
    for _ in range(8):
        ok, candidate = cap.read()
        if ok and candidate is not None:
            frame = candidate
        time.sleep(0.02)
    cap.release()

    if frame is None:
        return None

    ts = str(alert_row["ts"] or _iso_now())
    day = ts[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", ts) else _iso_now()[:10]
    out_dir = os.path.join(SNAPSHOT_DIR, day)
    os.makedirs(out_dir, exist_ok=True)
    file_name = (
        f"{ts.replace(':', '-')}_alert_{int(alert_row['id'])}_{_safe_name(alert_row['type'])}_{which}_fallback.jpg"
    )
    abs_path = os.path.join(out_dir, file_name)
    if not cv2.imwrite(abs_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88]):
        return None
    return abs_path


def _capture_alert_clip(alert_row) -> tuple[Optional[str], str]:
    if cv2 is None:
        return None, "opencv unavailable"
    if not _env_bool("TELEGRAM_SEND_CLIP", True):
        return None, "clip disabled"

    which, source_raw = _camera_source_for_alert(alert_row)
    source = _coerce_capture_source(source_raw)
    if source is None:
        return None, "camera source missing"

    fps = _env_float("TELEGRAM_CLIP_FPS", default=6.0, low=2.0, high=15.0)
    duration = _env_int("TELEGRAM_CLIP_SECONDS", default=4, low=2, high=12)
    frame_limit = max(1, int(round(fps * duration)))
    min_frames = max(3, int(round(fps * 1.3)))

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        cap.release()
        return None, "cannot open camera source"

    first_frame = None
    for _ in range(8):
        ok, frame = cap.read()
        if ok and frame is not None:
            first_frame = frame
            break
        time.sleep(0.05)
    if first_frame is None:
        cap.release()
        return None, "cannot read first frame"

    h, w = first_frame.shape[:2]
    ts = str(alert_row["ts"] or _iso_now())
    day = ts[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", ts) else _iso_now()[:10]
    out_dir = os.path.join(SNAPSHOT_DIR, day, "clips")
    os.makedirs(out_dir, exist_ok=True)
    file_name = f"{ts.replace(':', '-')}_alert_{int(alert_row['id'])}_{_safe_name(alert_row['type'])}_{which}.avi"
    abs_path = os.path.join(out_dir, file_name)

    writer = cv2.VideoWriter(abs_path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    if not writer.isOpened():
        cap.release()
        writer.release()
        return None, "cannot create video writer"

    frames_written = 0
    started = time.time()
    frame_interval = 1.0 / max(1.0, fps)
    next_deadline = time.time()

    try:
        while frames_written < frame_limit:
            now = time.time()
            if now < next_deadline:
                time.sleep(min(0.02, next_deadline - now))
                continue
            next_deadline = now + frame_interval

            ok, frame = cap.read()
            if not ok or frame is None:
                if (time.time() - started) > (duration + 3):
                    break
                continue
            if frame.shape[0] != h or frame.shape[1] != w:
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
            writer.write(frame)
            frames_written += 1
    finally:
        cap.release()
        writer.release()

    if frames_written < min_frames:
        try:
            os.remove(abs_path)
        except Exception:
            pass
        return None, f"insufficient clip frames ({frames_written})"

    return abs_path, f"frames={frames_written} fps={fps:.1f} seconds={duration}"


def _compose_media_caption(alert_row, media_kind: str) -> str:
    details = str(alert_row["details"] or "").strip()
    details_short = details[:200] + ("..." if len(details) > 200 else "")
    lines = [
        "Condo Monitoring System",
        f"{media_kind}: Alert #{int(alert_row['id'])}",
        f"Type: {alert_row['type']}",
        f"Area: {alert_row['room'] or '-'}",
        f"Time (UTC): {alert_row['ts']}",
    ]
    if details_short:
        lines.append(f"Notes: {details_short}")
    return "\n".join(lines)


class TelegramAlertNotifier:
    def __init__(self, logger):
        self.logger = logger
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.poll_seconds = _env_int("ALERT_NOTIFIER_POLL_SECONDS", default=5, low=2, high=120)
        self.fail_retry_seconds = _env_int("ALERT_NOTIFY_FAIL_RETRY_SECONDS", default=60, low=10, high=600)
        self.reminder_schedule = _env_schedule_seconds()
        self.repeat_seconds = _env_int("ALERT_REMINDER_REPEAT_SECONDS", default=600, low=30, high=3600)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="telegram-alert-notifier")
        self._thread.start()
        if telegram_is_configured():
            self.logger.info("Telegram notifier started with schedule=%s repeat=%ss", self.reminder_schedule, self.repeat_seconds)
        else:
            self.logger.warning("Telegram notifier is disabled (missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if telegram_is_configured():
                    self._tick()
            except Exception:
                self.logger.exception("Telegram notifier tick failed.")
            self._stop_event.wait(self.poll_seconds)

    def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        active_alerts = list_active_alerts(limit=300)
        for alert in active_alerts:
            if str(alert["status"]).upper() != "ACTIVE":
                continue
            should_send, is_initial = self._should_send(alert, now)
            if not should_send:
                continue
            message = _compose_alert_message(alert, is_initial=is_initial)
            ok, error = send_telegram_message(message)
            create_alert_notification_log(
                alert_id=int(alert["id"]),
                channel="TELEGRAM",
                kind="INITIAL" if is_initial else "REMINDER",
                ok=ok,
                message=message,
                error=error,
            )
            if ok:
                self.logger.info("Telegram %s sent for alert #%s", "initial" if is_initial else "reminder", alert["id"])
                if is_initial:
                    self._send_initial_media(alert)
            else:
                self.logger.warning("Telegram send failed for alert #%s: %s", alert["id"], error)

    def _send_initial_media(self, alert) -> None:
        if not _env_bool("TELEGRAM_SEND_MEDIA", True):
            return
        alert_type = str(alert["type"] or "").upper()
        if "OFFLINE" in alert_type:
            return

        alert_id = int(alert["id"])
        snapshot_abs = _alert_snapshot_abs_path(alert)
        if snapshot_abs is None:
            snapshot_abs = _capture_alert_snapshot_fallback(alert)

        if snapshot_abs is not None:
            ok_photo, err_photo = send_telegram_photo(
                snapshot_abs,
                caption=_compose_media_caption(alert, "Snapshot"),
            )
            create_alert_notification_log(
                alert_id=alert_id,
                channel="TELEGRAM",
                kind="MEDIA_PHOTO",
                ok=ok_photo,
                message=f"photo={os.path.basename(snapshot_abs)}",
                error=err_photo,
            )
            if ok_photo:
                self.logger.info("Telegram snapshot sent for alert #%s (%s)", alert_id, os.path.basename(snapshot_abs))
            else:
                self.logger.warning("Telegram snapshot send failed for alert #%s: %s", alert_id, err_photo)
        else:
            self.logger.warning("No snapshot available for alert #%s media send.", alert_id)

        clip_abs, clip_note = _capture_alert_clip(alert)
        if clip_abs is None:
            self.logger.warning("Clip capture skipped for alert #%s: %s", alert_id, clip_note)
            return

        ok_clip, err_clip = send_telegram_document(
            clip_abs,
            caption=_compose_media_caption(alert, "Clip"),
        )
        create_alert_notification_log(
            alert_id=alert_id,
            channel="TELEGRAM",
            kind="MEDIA_CLIP",
            ok=ok_clip,
            message=f"clip={os.path.basename(clip_abs)} | {clip_note}",
            error=err_clip,
        )
        if ok_clip:
            self.logger.info("Telegram clip sent for alert #%s (%s)", alert_id, os.path.basename(clip_abs))
        else:
            self.logger.warning("Telegram clip send failed for alert #%s: %s", alert_id, err_clip)

    def _should_send(self, alert, now: datetime) -> Tuple[bool, bool]:
        alert_ts = _parse_iso(alert["ts"])
        if not alert_ts:
            return False, False
        age_seconds = max(0.0, (now - alert_ts).total_seconds())
        alert_id = int(alert["id"])
        success_count = count_successful_notifications(alert_id, channel="TELEGRAM")
        last_attempt = get_last_notification_attempt(alert_id, channel="TELEGRAM")
        last_success = get_last_successful_notification(alert_id, channel="TELEGRAM")

        if last_attempt:
            last_attempt_ts = _parse_iso(last_attempt["attempt_ts"])
            if last_attempt_ts and (now - last_attempt_ts).total_seconds() < self.fail_retry_seconds:
                if int(last_attempt["ok"]) == 0:
                    return False, False

        if success_count < len(self.reminder_schedule):
            due_at = float(self.reminder_schedule[success_count])
            if age_seconds < due_at:
                return False, False
            is_initial = success_count == 0
            return True, is_initial

        if not last_success:
            return False, False
        last_success_ts = _parse_iso(last_success["attempt_ts"])
        if not last_success_ts:
            return False, False
        if (now - last_success_ts).total_seconds() >= self.repeat_seconds:
            return True, False
        return False, False
