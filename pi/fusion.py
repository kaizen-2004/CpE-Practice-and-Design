from typing import Optional

from db import (
    create_alert,
    attach_snapshot_to_alert,
    get_latest_snapshot,
    get_latest_event,
    has_recent_event,
    has_recent_alert,
    get_guest_mode,
)
from config import (
    FIRE_FUSION_WINDOW,
    INTRUDER_FUSION_WINDOW,
    FIRE_COOLDOWN_SECONDS,
    INTRUDER_COOLDOWN_SECONDS,
    EVENT_SMOKE_HIGH,
    EVENT_FLAME_SIGNAL,
    EVENT_DOOR_FORCE,
    EVENT_UNKNOWN,
)


def handle_fire_signal(ts: str, room: str = "", cooldown_seconds: Optional[int] = None, window_seconds: Optional[int] = None) -> Optional[int]:
    window = window_seconds if window_seconds is not None else FIRE_FUSION_WINDOW
    cooldown = cooldown_seconds if cooldown_seconds is not None else FIRE_COOLDOWN_SECONDS
    has_smoke = has_recent_event(EVENT_SMOKE_HIGH, within_seconds=window, ts=ts)
    has_flame = has_recent_event(EVENT_FLAME_SIGNAL, source="CAM_INDOOR", within_seconds=window, ts=ts)
    if not (has_smoke and has_flame):
        return None
    if has_recent_alert("FIRE", within_seconds=cooldown, ts=ts):
        return None

    flame_event = get_latest_event(EVENT_FLAME_SIGNAL, source="CAM_INDOOR")
    smoke_event = get_latest_event(EVENT_SMOKE_HIGH)

    alert_room = ""
    if flame_event and flame_event["room"]:
        alert_room = flame_event["room"]
    elif smoke_event and smoke_event["room"]:
        alert_room = smoke_event["room"]
    elif room:
        alert_room = room
    if not alert_room:
        alert_room = "Living Room"

    details = "Fusion: flame + smoke evidence"
    if flame_event and smoke_event:
        details = f"Fusion: flame({flame_event['ts']}) + smoke({smoke_event['ts']})"

    alert_id = create_alert(
        "FIRE",
        room=alert_room,
        severity=3,
        status="ACTIVE",
        details=details,
        snapshot_path="",
        ts=ts,
    )

    snap = get_latest_snapshot(snapshot_type=EVENT_FLAME_SIGNAL, label="FLAME")
    if snap:
        attach_snapshot_to_alert(alert_id, snap["file_relpath"])

    return alert_id


def handle_intruder_evidence(ts: str, room: str = "", cooldown_seconds: Optional[int] = None, window_seconds: Optional[int] = None) -> Optional[int]:
    if get_guest_mode():
        return None

    window = window_seconds if window_seconds is not None else INTRUDER_FUSION_WINDOW
    cooldown = cooldown_seconds if cooldown_seconds is not None else INTRUDER_COOLDOWN_SECONDS

    has_outdoor = has_recent_event(EVENT_UNKNOWN, source="CAM_OUTDOOR", within_seconds=window, ts=ts)
    has_indoor = has_recent_event(EVENT_UNKNOWN, source="CAM_INDOOR", within_seconds=window, ts=ts)
    has_force = has_recent_event(EVENT_DOOR_FORCE, within_seconds=window, ts=ts)

    evidence_count = int(has_outdoor) + int(has_indoor) + int(has_force)
    if evidence_count < 2:
        return None

    if has_recent_alert("INTRUDER", within_seconds=cooldown, ts=ts):
        return None

    evidence = []
    if has_outdoor:
        evidence.append("outdoor unknown")
    if has_indoor:
        evidence.append("indoor unknown")
    if has_force:
        evidence.append("door-force")

    alert_room = "Door Entrance Area" if (has_outdoor or has_force) else "Living Room"

    alert_id = create_alert(
        "INTRUDER",
        room=alert_room,
        severity=3,
        status="ACTIVE",
        details="Evidence: " + ", ".join(evidence),
        snapshot_path="",
        ts=ts,
    )

    snap = get_latest_snapshot(snapshot_type="FACE_UNKNOWN", label="UNKNOWN")
    if snap:
        attach_snapshot_to_alert(alert_id, snap["file_relpath"])

    return alert_id
