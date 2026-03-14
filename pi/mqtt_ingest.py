#!/usr/bin/env python3
"""MQTT ingestion bridge: subscribe to sensor topics and forward to Flask API.

Default flow:
  MQTT topic -> pi/mqtt_ingest.py -> HTTP POST /api/sensors/event -> Flask
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from threading import Event
from typing import Any, Deque, Dict, Optional

from mqtt_schema import decode_json, normalize_message, topic_filters

try:
    import paho.mqtt.client as mqtt
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "paho-mqtt is required for mqtt_ingest.py.\n"
        "Install with: pip install paho-mqtt\n\n"
        f"Original error: {exc}"
    ) from exc


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


@dataclass
class PendingItem:
    payload: Dict[str, Any]
    topic: str
    next_attempt_at: float
    attempts: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MQTT bridge to /api/sensors/event")
    parser.add_argument("--broker-host", default=os.environ.get("MQTT_BROKER_HOST", "127.0.0.1"))
    parser.add_argument("--broker-port", type=int, default=int(os.environ.get("MQTT_BROKER_PORT", "1883")))
    parser.add_argument("--broker-username", default=os.environ.get("MQTT_BROKER_USERNAME", ""))
    parser.add_argument("--broker-password", default=os.environ.get("MQTT_BROKER_PASSWORD", ""))
    parser.add_argument("--client-id", default=os.environ.get("MQTT_INGEST_CLIENT_ID", "thesis-mqtt-ingest"))
    parser.add_argument("--topic-root", default=os.environ.get("MQTT_TOPIC_ROOT", "thesis/v1"))
    parser.add_argument(
        "--api-url",
        default=os.environ.get("SENSOR_EVENT_URL", "http://127.0.0.1:5000/api/sensors/event"),
    )
    parser.add_argument("--api-key", default=os.environ.get("SENSOR_API_KEY", ""))
    parser.add_argument("--http-timeout", type=float, default=float(os.environ.get("MQTT_INGEST_HTTP_TIMEOUT", "4.0")))
    parser.add_argument(
        "--retry-seconds",
        type=float,
        default=float(os.environ.get("MQTT_INGEST_RETRY_SECONDS", "5.0")),
    )
    parser.add_argument(
        "--status-interval",
        type=float,
        default=float(os.environ.get("MQTT_INGEST_STATUS_INTERVAL", "20.0")),
    )
    parser.add_argument("--max-pending", type=int, default=int(os.environ.get("MQTT_INGEST_MAX_PENDING", "400")))
    parser.add_argument("--qos", type=int, default=int(os.environ.get("MQTT_INGEST_QOS", "1")))
    parser.add_argument(
        "--dedupe-window-seconds",
        type=float,
        default=float(os.environ.get("MQTT_INGEST_DEDUPE_WINDOW", "600")),
    )
    return parser.parse_args()


def post_event(payload: Dict[str, Any], api_url: str, api_key: str, timeout: float) -> tuple[bool, str]:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key

    req = urllib.request.Request(api_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ok = 200 <= resp.status < 300
            return ok, f"code={resp.status} body={body[:180]}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        return False, f"http_error={exc.code} body={body[:180]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"error={exc}"


def queue_pending(
    pending: Deque[PendingItem],
    item: PendingItem,
    retry_seconds: float,
    max_pending: int,
) -> None:
    while len(pending) >= max_pending:
        dropped = pending.popleft()
        print(
            f"[mqtt-ingest] pending full; dropping oldest node={dropped.payload.get('node')} "
            f"event={dropped.payload.get('event')}",
            flush=True,
        )
    item.next_attempt_at = time.time() + retry_seconds
    pending.append(item)


def process_pending(
    pending: Deque[PendingItem],
    api_url: str,
    api_key: str,
    http_timeout: float,
    retry_seconds: float,
    max_pending: int,
) -> tuple[int, int]:
    now = time.time()
    delivered = 0
    failed = 0

    rounds = len(pending)
    for _ in range(rounds):
        item = pending.popleft()
        if item.next_attempt_at > now:
            pending.append(item)
            continue

        ok, detail = post_event(item.payload, api_url, api_key, http_timeout)
        if ok:
            delivered += 1
            print(
                f"[mqtt-ingest] retry delivered node={item.payload.get('node')} "
                f"event={item.payload.get('event')} {detail}",
                flush=True,
            )
            continue

        failed += 1
        queue_pending(
            pending=pending,
            item=PendingItem(
                payload=item.payload,
                topic=item.topic,
                next_attempt_at=time.time() + retry_seconds,
                attempts=item.attempts + 1,
            ),
            retry_seconds=retry_seconds,
            max_pending=max_pending,
        )
        print(
            f"[mqtt-ingest] retry failed node={item.payload.get('node')} event={item.payload.get('event')} "
            f"attempts={item.attempts + 1} {detail}",
            flush=True,
        )

    return delivered, failed


class SeqDedupe:
    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = max(0.0, float(window_seconds))
        self._last_by_node: Dict[str, tuple[int, float]] = {}

    def is_duplicate(self, node: str, seq: Optional[int]) -> bool:
        if seq is None:
            return False
        now = time.time()
        old = self._last_by_node.get(node)
        self._last_by_node[node] = (int(seq), now)
        if not old:
            return False
        prev_seq, prev_ts = old
        if now - prev_ts > self.window_seconds:
            return False
        return int(seq) == int(prev_seq)


def main() -> int:
    args = parse_args()
    stop_event = Event()

    def _stop(_sig: int, _frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    pending: Deque[PendingItem] = deque()
    dedupe = SeqDedupe(window_seconds=args.dedupe_window_seconds)

    stats = {
        "rx": 0,
        "parsed": 0,
        "forward_ok": 0,
        "forward_fail": 0,
        "dropped_parse": 0,
        "dropped_dupe": 0,
    }
    last_status = time.time()

    client = mqtt.Client(client_id=args.client_id, clean_session=True)
    if args.broker_username:
        client.username_pw_set(args.broker_username, args.broker_password)

    def on_connect(_client: mqtt.Client, _userdata: Any, _flags: Dict[str, Any], rc: int) -> None:
        if rc != 0:
            print(f"[mqtt-ingest] mqtt connect failed rc={rc}", flush=True)
            return
        print(
            f"[mqtt-ingest] connected to {args.broker_host}:{args.broker_port}, topic_root={args.topic_root}",
            flush=True,
        )
        for flt in topic_filters(args.topic_root):
            client.subscribe(flt, qos=max(0, min(2, int(args.qos))))
            print(f"[mqtt-ingest] subscribed {flt}", flush=True)

    def on_disconnect(_client: mqtt.Client, _userdata: Any, rc: int) -> None:
        print(f"[mqtt-ingest] disconnected rc={rc}", flush=True)

    def on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        stats["rx"] += 1
        try:
            payload_obj = decode_json(msg.payload)
            normalized = normalize_message(msg.topic, payload_obj, topic_root=args.topic_root)
            if dedupe.is_duplicate(normalized.node, normalized.seq):
                stats["dropped_dupe"] += 1
                return
            api_payload = normalized.to_api_payload()
            queue_pending(
                pending=pending,
                item=PendingItem(payload=api_payload, topic=msg.topic, next_attempt_at=time.time(), attempts=0),
                retry_seconds=args.retry_seconds,
                max_pending=args.max_pending,
            )
            stats["parsed"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["dropped_parse"] += 1
            print(f"[mqtt-ingest] dropped message topic={msg.topic}: {exc}", flush=True)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        client.connect(args.broker_host, args.broker_port, keepalive=45)
    except Exception as exc:  # noqa: BLE001
        print(f"[mqtt-ingest] initial mqtt connect failed: {exc}", file=sys.stderr, flush=True)

    while not stop_event.is_set():
        try:
            client.loop(timeout=1.0)
        except Exception as exc:  # noqa: BLE001
            print(f"[mqtt-ingest] loop error: {exc}", flush=True)
            time.sleep(1.0)

        delivered, failed = process_pending(
            pending=pending,
            api_url=args.api_url,
            api_key=args.api_key,
            http_timeout=args.http_timeout,
            retry_seconds=args.retry_seconds,
            max_pending=args.max_pending,
        )
        stats["forward_ok"] += delivered
        stats["forward_fail"] += failed

        now = time.time()
        if now - last_status >= args.status_interval:
            last_status = now
            print(
                "[mqtt-ingest] status "
                f"rx={stats['rx']} parsed={stats['parsed']} ok={stats['forward_ok']} fail={stats['forward_fail']} "
                f"pending={len(pending)} dropped_parse={stats['dropped_parse']} dropped_dupe={stats['dropped_dupe']}",
                flush=True,
            )

    try:
        client.disconnect()
    except Exception:
        pass
    print("[mqtt-ingest] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
