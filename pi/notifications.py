import os
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from db import (
    list_active_alerts,
    create_alert_notification_log,
    get_last_notification_attempt,
    get_last_successful_notification,
    count_successful_notifications,
)


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


def _telegram_api_url() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    return f"https://api.telegram.org/bot{token}/sendMessage"


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
    req = urllib_request.Request(_telegram_api_url(), data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            if 200 <= int(resp.status) < 300:
                return True, ""
            return False, f"http status {resp.status}"
    except Exception as exc:
        return False, str(exc)


def send_telegram_test_message() -> Tuple[bool, str]:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip()
    text = "Condo Monitoring System\nTelegram connection test is successful."
    if base:
        text += f"\nDashboard: {base.rstrip('/')}/dashboard"
    return send_telegram_message(text)


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
            else:
                self.logger.warning("Telegram send failed for alert #%s: %s", alert["id"], error)

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
