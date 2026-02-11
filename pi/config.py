import os
from typing import Dict

ROOMS = ["Living Room", "Door Entrance Area"]

EVENT_SMOKE_HIGH = "SMOKE_HIGH"
EVENT_FLAME_SIGNAL = "FLAME_SIGNAL"
EVENT_DOOR_FORCE = "DOOR_FORCE"
EVENT_UNKNOWN = "UNKNOWN"
EVENT_AUTHORIZED = "AUTHORIZED"

NODE_META: Dict[str, Dict[str, str]] = {
    "mq2_living": {
        "label": "MQ-2 Smoke Sensor",
        "room": "Living Room",
        "kind": "sensor",
        "role": "smoke",
    },
    "mq2_door": {
        "label": "MQ-2 Smoke Sensor",
        "room": "Door Entrance Area",
        "kind": "sensor",
        "role": "smoke",
    },
    "door_force": {
        "label": "Door-Force Sensor",
        "room": "Door Entrance Area",
        "kind": "sensor",
        "role": "door_force",
    },
    "cam_indoor": {
        "label": "Indoor Camera",
        "room": "Living Room",
        "kind": "camera",
        "role": "indoor",
    },
    "cam_outdoor": {
        "label": "Outdoor Camera",
        "room": "Door Entrance Area",
        "kind": "camera",
        "role": "outdoor",
    },
}

NODE_ALIASES = {
    "mq2_living_room": "mq2_living",
    "mq2_livingroom": "mq2_living",
    "mq2_entrance": "mq2_door",
    "mq2_door_entrance": "mq2_door",
    "door_node": "door_force",
    "doorforce": "door_force",
    "door_force_sensor": "door_force",
    "cam_inside": "cam_indoor",
    "cam_outside": "cam_outdoor",
    "mq2_kitchen": "mq2_living",
}

FIRE_FUSION_WINDOW = int(os.environ.get("FIRE_FUSION_WINDOW", "120"))
INTRUDER_FUSION_WINDOW = int(os.environ.get("INTRUDER_FUSION_WINDOW", "120"))
NODE_OFFLINE_SECONDS = int(os.environ.get("NODE_OFFLINE_SECONDS", "180"))
FIRE_COOLDOWN_SECONDS = int(os.environ.get("FIRE_COOLDOWN", "75"))
INTRUDER_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN", "45"))


def normalize_node_id(raw: str) -> str:
    s = str(raw or "").strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = "".join(ch for ch in s if ch.isalnum() or ch == "_")
    if s in NODE_ALIASES:
        return NODE_ALIASES[s]
    return s


def get_node_meta(node_id: str) -> Dict[str, str]:
    return NODE_META.get(node_id, {"label": node_id, "room": "", "kind": "unknown", "role": ""})
