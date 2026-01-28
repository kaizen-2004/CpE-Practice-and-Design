import os
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

import cv2
import numpy as np

from db import SNAPSHOT_DIR

FACE_SIZE = (200, 200)

def _safe(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_\- ]+", "", s)
    s = re.sub(r"\s+", "_", s)
    return s or "x"

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def save_frame_snapshot(frame_bgr: np.ndarray, prefix: str, ts_iso: Optional[str] = None) -> Tuple[str, str]:
    """
    Save a BGR frame under snapshots/YYYY-MM-DD/<ts>_<prefix>.jpg
    Returns (file_relpath, abs_path)
    """
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds") if not ts_iso else ts_iso
    day = ts[:10]
    day_dir = os.path.join(SNAPSHOT_DIR, day)
    ensure_dir(day_dir)

    fname = ts.replace(":", "-") + f"_{_safe(prefix)}.jpg"
    rel = os.path.join(day, fname).replace("\\", "/")
    abs_path = os.path.join(SNAPSHOT_DIR, rel)

    cv2.imwrite(abs_path, frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return rel, abs_path

def _largest_face(rects):
    if rects is None or len(rects) == 0:
        return None
    return max(rects, key=lambda r: r[2]*r[3])

def extract_face_roi(image_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Return grayscale 200x200 face ROI (largest face), or None."""
    if image_bgr is None:
        return None
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    rects = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
    r = _largest_face(rects)
    if r is None:
        return None
    x, y, w, h = r
    roi = gray[y:y+h, x:x+w]
    roi = cv2.resize(roi, FACE_SIZE, interpolation=cv2.INTER_AREA)
    return roi

def export_face_sample_from_snapshot(snapshot_abs_path: str, dataset_face_dir: str, out_name: str) -> Optional[str]:
    """
    Load snapshot image, detect largest face, save as grayscale sample in dataset_face_dir.
    Returns saved path or None.
    """
    ensure_dir(dataset_face_dir)
    img = cv2.imread(snapshot_abs_path)
    roi = extract_face_roi(img)
    if roi is None:
        return None
    out_path = os.path.join(dataset_face_dir, out_name)
    cv2.imwrite(out_path, roi)
    return out_path
