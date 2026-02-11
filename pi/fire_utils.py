import json
import os
from typing import Optional, Tuple

import cv2
import numpy as np


def flame_ratio(frame_bgr: np.ndarray) -> float:
    """Estimate flame-like pixel ratio in a BGR frame."""
    if frame_bgr is None or frame_bgr.size == 0:
        return 0.0
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, (0, 120, 120), (35, 255, 255))
    mask2 = cv2.inRange(hsv, (160, 120, 120), (179, 255, 255))
    mask = cv2.bitwise_or(mask1, mask2)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return float(mask.mean() / 255.0)


def load_fire_model(model_path: str) -> Optional[dict]:
    if not os.path.exists(model_path):
        return None
    try:
        with open(model_path, "r", encoding="utf-8") as f:
            model = json.load(f)
        if "ratio_threshold" not in model:
            return None
        model["ratio_threshold"] = float(model["ratio_threshold"])
        return model
    except Exception:
        return None


def detect_flame_signal(frame_bgr: np.ndarray, threshold: float) -> Tuple[bool, float]:
    ratio = flame_ratio(frame_bgr)
    return ratio >= float(threshold), ratio
