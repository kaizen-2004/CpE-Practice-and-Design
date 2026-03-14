from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import get_node_meta, normalize_node_id


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_ts(ts_raw: Any) -> Optional[str]:
    if ts_raw is None:
        return None
    if isinstance(ts_raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts_raw), tz=timezone.utc).isoformat(timespec="seconds")
        except Exception:
            return None
    ts = str(ts_raw).strip()
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def topic_filters(topic_root: str) -> List[str]:
    base = topic_root.strip().strip("/")
    return [
        f"{base}/events/+",
        f"{base}/status/+",
        f"{base}/camera/+/ack",
    ]


def _status_event_for_node(node: str) -> str:
    if node in ("mq2_living", "mq2_door"):
        return "SMOKE_HEARTBEAT"
    if node == "door_force":
        return "DOOR_HEARTBEAT"
    if node in ("cam_indoor", "cam_outdoor"):
        return "CAM_HEARTBEAT"
    return "NODE_HEARTBEAT"


def _offline_event_for_node(node: str) -> str:
    if node == "door_force":
        return "DOOR_SENSOR_OFFLINE"
    if node in ("mq2_living", "mq2_door"):
        return "SMOKE_SENSOR_OFFLINE"
    if node in ("cam_indoor", "cam_outdoor"):
        return "CAMERA_OFFLINE"
    return "NODE_OFFLINE"


def _status_note(payload: Dict[str, Any]) -> str:
    parts = []
    if "s" in payload:
        parts.append(f"online={1 if int(payload.get('s') or 0) else 0}")
    if "r" in payload:
        parts.append(f"rssi={payload.get('r')}")
    if "m" in payload and str(payload.get("m", "")).strip():
        parts.append(str(payload.get("m")).strip())
    return " ".join(parts).strip()


@dataclass
class NormalizedMessage:
    node: str
    event: str
    room: str
    value: Any
    unit: str
    note: str
    ts: str
    seq: Optional[int]
    topic: str

    def to_api_payload(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "node": self.node,
            "event": self.event,
            "room": self.room,
            "ts": self.ts,
        }
        if self.value is not None:
            out["value"] = self.value
        if self.unit:
            out["unit"] = self.unit
        if self.note:
            out["note"] = self.note
        return out


def decode_json(payload_bytes: bytes) -> Dict[str, Any]:
    if not payload_bytes:
        raise ValueError("empty payload")
    try:
        raw = payload_bytes.decode("utf-8", errors="strict")
    except Exception as exc:
        raise ValueError(f"payload is not valid utf-8: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"payload is not valid json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("payload json must be an object")
    return parsed


def normalize_message(topic: str, payload_obj: Dict[str, Any], topic_root: str) -> NormalizedMessage:
    base = topic_root.strip().strip("/")
    t = topic.strip().strip("/")
    if not t.startswith(base + "/"):
        raise ValueError(f"topic outside root '{base}': {topic}")

    parts = t.split("/")
    if len(parts) < 3:
        raise ValueError(f"invalid topic structure: {topic}")

    if parts[0] != base.split("/")[0]:
        # Handle cases where topic_root has nested levels (e.g., thesis/v1)
        base_parts = base.split("/")
        if parts[: len(base_parts)] != base_parts:
            raise ValueError(f"topic outside root '{base}': {topic}")
        parts = parts[len(base_parts) :]
    else:
        base_parts = base.split("/")
        parts = parts[len(base_parts) :]

    if not parts:
        raise ValueError(f"invalid topic structure: {topic}")

    channel = parts[0]
    node = normalize_node_id(parts[1]) if len(parts) >= 2 else ""
    if not node:
        raise ValueError("node id not found in topic")
    meta = get_node_meta(node)

    seq_raw = payload_obj.get("q", payload_obj.get("seq"))
    seq: Optional[int] = None
    if seq_raw is not None and str(seq_raw).strip() != "":
        try:
            seq = int(seq_raw)
        except Exception:
            seq = None

    ts = _coerce_ts(payload_obj.get("t", payload_obj.get("ts"))) or _iso_utc_now()

    if channel == "events":
        event = str(payload_obj.get("e", payload_obj.get("event", ""))).strip().upper()
        if not event:
            raise ValueError("event payload missing 'e'/'event'")
        value = payload_obj.get("x", payload_obj.get("value"))
        unit = str(payload_obj.get("u", payload_obj.get("unit", ""))).strip()
        note = str(payload_obj.get("m", payload_obj.get("note", ""))).strip()
        room = str(payload_obj.get("room") or meta.get("room", "")).strip()
        return NormalizedMessage(
            node=node,
            event=event,
            room=room,
            value=value,
            unit=unit,
            note=note,
            ts=ts,
            seq=seq,
            topic=topic,
        )

    if channel == "status":
        online_raw = payload_obj.get("s")
        online: Optional[int] = None
        if online_raw is not None:
            try:
                online = 1 if int(online_raw) else 0
            except Exception:
                online = None

        event = str(payload_obj.get("e", "")).strip().upper()
        if not event:
            event = _offline_event_for_node(node) if online == 0 else _status_event_for_node(node)
        room = str(payload_obj.get("room") or meta.get("room", "")).strip()
        value = payload_obj.get("x", payload_obj.get("value"))
        unit = str(payload_obj.get("u", payload_obj.get("unit", ""))).strip()
        note = str(payload_obj.get("m", payload_obj.get("note", ""))).strip()
        if not note:
            note = _status_note(payload_obj)
        return NormalizedMessage(
            node=node,
            event=event,
            room=room,
            value=value,
            unit=unit,
            note=note,
            ts=ts,
            seq=seq,
            topic=topic,
        )

    if channel == "camera" and len(parts) >= 3 and parts[2] == "ack":
        room = str(payload_obj.get("room") or meta.get("room", "")).strip()
        note = str(payload_obj.get("m", payload_obj.get("note", ""))).strip()
        if not note:
            ok_raw = payload_obj.get("ok")
            if ok_raw is not None:
                note = f"camera_ack ok={ok_raw}"
            else:
                note = "camera_ack"
        return NormalizedMessage(
            node=node,
            event="CAM_CONTROL_ACK",
            room=room,
            value=payload_obj.get("x", payload_obj.get("value")),
            unit=str(payload_obj.get("u", payload_obj.get("unit", ""))).strip(),
            note=note,
            ts=ts,
            seq=seq,
            topic=topic,
        )

    raise ValueError(f"unsupported topic channel '{channel}' for topic '{topic}'")
