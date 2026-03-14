#!/usr/bin/env python3
"""Ingest ESP-NOW gateway serial JSON and forward to Flask sensor API.

Usage:
  python3 pi/serial_ingest.py --port /dev/ttyACM0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional

import serial


@dataclass
class PendingItem:
    payload: Dict[str, Any]
    next_attempt_at: float
    attempts: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESP-NOW serial bridge to /api/sensors/event")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial port path (default: /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:5000/api/sensors/event",
        help="Flask endpoint URL (default: http://127.0.0.1:5000/api/sensors/event)",
    )
    parser.add_argument("--api-key", default="", help="Optional X-API-KEY header")
    parser.add_argument("--serial-timeout", type=float, default=0.5, help="Serial read timeout seconds")
    parser.add_argument("--http-timeout", type=float, default=4.0, help="HTTP request timeout seconds")
    parser.add_argument("--retry-seconds", type=float, default=5.0, help="Retry delay for failed posts")
    parser.add_argument("--max-pending", type=int, default=200, help="Max pending queue size before dropping oldest")
    parser.add_argument("--status-interval", type=float, default=20.0, help="Seconds between status prints")
    return parser.parse_args()


def post_event(payload: Dict[str, Any], server_url: str, api_key: str, timeout: float) -> tuple[bool, str]:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key

    req = urllib.request.Request(server_url, data=data, headers=headers, method="POST")

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


def normalize_payload(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    node = str(raw.get("node", "")).strip()
    event = str(raw.get("event", "")).strip().upper()
    room = str(raw.get("room", "")).strip()

    if not node or not event:
        return None

    payload: Dict[str, Any] = {
        "node": node,
        "event": event,
    }

    if room:
        payload["room"] = room

    if "value" in raw:
        payload["value"] = raw.get("value")
    if "unit" in raw and str(raw.get("unit", "")).strip():
        payload["unit"] = str(raw.get("unit", "")).strip()
    if "note" in raw and str(raw.get("note", "")).strip():
        payload["note"] = str(raw.get("note", "")).strip()
    if "ts" in raw and str(raw.get("ts", "")).strip():
        payload["ts"] = str(raw.get("ts", "")).strip()

    return payload


def queue_pending(
    pending: Deque[PendingItem],
    payload: Dict[str, Any],
    retry_seconds: float,
    max_pending: int,
    attempts: int,
) -> None:
    while len(pending) >= max_pending:
        dropped = pending.popleft()
        print(
            f"[bridge] pending queue full; dropping oldest node={dropped.payload.get('node')} event={dropped.payload.get('event')}",
            flush=True,
        )

    pending.append(PendingItem(payload=payload, next_attempt_at=time.time() + retry_seconds, attempts=attempts))


def process_pending(
    pending: Deque[PendingItem],
    server_url: str,
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

        ok, detail = post_event(item.payload, server_url, api_key, http_timeout)
        if ok:
            delivered += 1
            print(
                f"[bridge] retry delivered node={item.payload.get('node')} event={item.payload.get('event')} {detail}",
                flush=True,
            )
            continue

        failed += 1
        queue_pending(
            pending=pending,
            payload=item.payload,
            retry_seconds=retry_seconds,
            max_pending=max_pending,
            attempts=item.attempts + 1,
        )
        print(
            f"[bridge] retry failed node={item.payload.get('node')} event={item.payload.get('event')} attempts={item.attempts + 1} {detail}",
            flush=True,
        )

    return delivered, failed


def main() -> int:
    args = parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=args.serial_timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"[bridge] failed to open serial port {args.port}: {exc}", file=sys.stderr)
        return 1

    print(
        f"[bridge] listening on {args.port}@{args.baud}, forwarding to {args.server_url}",
        flush=True,
    )

    pending: Deque[PendingItem] = deque()

    rx_lines = 0
    rx_events = 0
    tx_ok = 0
    tx_fail = 0
    bad_lines = 0

    last_status = time.time()

    try:
        while True:
            delivered, failed = process_pending(
                pending=pending,
                server_url=args.server_url,
                api_key=args.api_key,
                http_timeout=args.http_timeout,
                retry_seconds=args.retry_seconds,
                max_pending=args.max_pending,
            )
            tx_ok += delivered
            tx_fail += failed

            raw = ser.readline()
            if raw:
                rx_lines += 1
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                if not line.startswith("{"):
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
                    print(f"[bridge] bad json line: {line[:180]}", flush=True)
                    continue

                payload = normalize_payload(event)
                if not payload:
                    bad_lines += 1
                    print(f"[bridge] dropped invalid payload: {line[:180]}", flush=True)
                    continue

                rx_events += 1
                ok, detail = post_event(payload, args.server_url, args.api_key, args.http_timeout)
                if ok:
                    tx_ok += 1
                else:
                    tx_fail += 1
                    queue_pending(
                        pending=pending,
                        payload=payload,
                        retry_seconds=args.retry_seconds,
                        max_pending=args.max_pending,
                        attempts=1,
                    )
                    print(
                        f"[bridge] post failed node={payload.get('node')} event={payload.get('event')} {detail}",
                        flush=True,
                    )

            now = time.time()
            if (now - last_status) >= args.status_interval:
                last_status = now
                print(
                    "[bridge] status "
                    f"rx_lines={rx_lines} rx_events={rx_events} tx_ok={tx_ok} tx_fail={tx_fail} "
                    f"pending={len(pending)} bad_lines={bad_lines}",
                    flush=True,
                )

    except KeyboardInterrupt:
        print("\n[bridge] stopping on Ctrl+C", flush=True)
    finally:
        ser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
