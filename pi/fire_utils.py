import json
import os
from typing import Optional, Tuple

import cv2
import numpy as np


def _flame_mask(frame_bgr: np.ndarray) -> np.ndarray:
    """Return binary mask of flame-like pixels."""
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, (0, 120, 120), (35, 255, 255))
    mask2 = cv2.inRange(hsv, (160, 120, 120), (179, 255, 255))
    mask = cv2.bitwise_or(mask1, mask2)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask


def flame_metrics(frame_bgr: np.ndarray) -> Tuple[float, float, float]:
    """
    Return flame metrics as (ratio, largest_blob_ratio, hot_core_ratio).
    ratio: proportion of warm flame-like pixels.
    largest_blob_ratio: area ratio of the largest connected flame component.
    hot_core_ratio: proportion of very bright warm pixels (filters orange objects).
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return 0.0, 0.0, 0.0
    mask = _flame_mask(frame_bgr)

    total_pixels = float(mask.shape[0] * mask.shape[1])
    ratio = float(mask.mean() / 255.0)

    # Use connected components to avoid triggering on scattered orange noise.
    num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    largest_blob = 0
    if num_labels > 1:
        largest_blob = int(stats[1:, cv2.CC_STAT_AREA].max())
    largest_blob_ratio = float(largest_blob / total_pixels)

    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    hot1 = cv2.inRange(hsv, (0, 100, 225), (45, 255, 255))
    hot2 = cv2.inRange(hsv, (160, 100, 225), (179, 255, 255))
    hot = cv2.bitwise_or(hot1, hot2)
    hot = cv2.bitwise_and(hot, mask)
    hot_core_ratio = float(hot.mean() / 255.0)

    return ratio, largest_blob_ratio, hot_core_ratio


def flame_ratio(frame_bgr: np.ndarray) -> float:
    """Estimate flame-like pixel ratio in a BGR frame."""
    ratio, _largest_blob_ratio, _hot_core_ratio = flame_metrics(frame_bgr)
    return ratio


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


def detect_flame_signal(
    frame_bgr: np.ndarray,
    threshold: float,
    min_blob_ratio: float = 0.0,
    min_hot_ratio: float = 0.0,
) -> Tuple[bool, float]:
    ratio, largest_blob_ratio, hot_core_ratio = flame_metrics(frame_bgr)
    is_flame = (
        ratio >= float(threshold)
        and largest_blob_ratio >= float(min_blob_ratio)
        and hot_core_ratio >= float(min_hot_ratio)
    )
    return is_flame, ratio
