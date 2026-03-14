import os
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

import cv2
import numpy as np

from db import SNAPSHOT_DIR

FACE_SIZE = (200, 200)
_FACE_CASCADE = None
_FACE_CASCADE_PATH = None
_FACE_CASCADE_WARNED = False
_HAAR_FRONTALFACE_XML = "haarcascade_frontalface_default.xml"

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

def _face_cascade():
    global _FACE_CASCADE_PATH, _FACE_CASCADE_WARNED
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        candidates = []
        cv2_data = getattr(cv2, "data", None)
        haar_root = getattr(cv2_data, "haarcascades", "") if cv2_data is not None else ""
        if haar_root:
            candidates.append(os.path.join(haar_root, _HAAR_FRONTALFACE_XML))

        cv2_file = getattr(cv2, "__file__", "")
        if cv2_file:
            cv2_dir = os.path.dirname(os.path.abspath(cv2_file))
            candidates.extend(
                [
                    os.path.join(cv2_dir, "data", _HAAR_FRONTALFACE_XML),
                    os.path.join(cv2_dir, "..", "share", "opencv4", "haarcascades", _HAAR_FRONTALFACE_XML),
                    os.path.join(cv2_dir, "..", "share", "opencv", "haarcascades", _HAAR_FRONTALFACE_XML),
                ]
            )

        candidates.extend(
            [
                os.path.join("/usr/share/opencv4/haarcascades", _HAAR_FRONTALFACE_XML),
                os.path.join("/usr/share/opencv/haarcascades", _HAAR_FRONTALFACE_XML),
                os.path.join("/usr/local/share/opencv4/haarcascades", _HAAR_FRONTALFACE_XML),
                os.path.join("/usr/local/share/opencv/haarcascades", _HAAR_FRONTALFACE_XML),
            ]
        )

        for path in candidates:
            if not path:
                continue
            full = os.path.abspath(path)
            if not os.path.isfile(full):
                continue
            cascade = cv2.CascadeClassifier(full)
            if cascade is not None and not cascade.empty():
                _FACE_CASCADE = cascade
                _FACE_CASCADE_PATH = full
                break

        if _FACE_CASCADE is None and not _FACE_CASCADE_WARNED:
            _FACE_CASCADE_WARNED = True
            print(
                "[vision_utils] Warning: OpenCV Haar cascade not found; face detection disabled."
            )
    return _FACE_CASCADE

def detect_face_rects(gray_image: np.ndarray):
    """Return detected face rectangles sorted by area descending."""
    if gray_image is None:
        return []
    cascade = _face_cascade()
    if cascade is None or cascade.empty():
        return []
    rects = cascade.detectMultiScale(gray_image, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
    if rects is None or len(rects) == 0:
        return []
    rows = [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in rects]
    rows.sort(key=lambda r: r[2] * r[3], reverse=True)
    return rows

def preprocess_face_roi(gray_image: np.ndarray, rect):
    """Crop + resize one detected face into grayscale FACE_SIZE."""
    if gray_image is None or rect is None:
        return None
    x, y, w, h = rect
    h_img, w_img = gray_image.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(w_img, x + w)
    y2 = min(h_img, y + h)
    if x2 <= x1 or y2 <= y1:
        return None
    roi = gray_image[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    return cv2.resize(roi, FACE_SIZE, interpolation=cv2.INTER_AREA)

def detect_preprocess_faces(image_bgr: np.ndarray):
    """Detect faces in BGR frame and return [{'rect': (x,y,w,h), 'roi': gray_200x200}, ...]."""
    if image_bgr is None:
        return []
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    out = []
    for rect in detect_face_rects(gray):
        roi = preprocess_face_roi(gray, rect)
        if roi is None:
            continue
        out.append({"rect": rect, "roi": roi})
    return out

def classify_face_roi(face_roi: np.ndarray, recognizer, id_to_name: dict, unknown_threshold: float):
    """Predict one preprocessed face ROI with LBPH and apply threshold."""
    label = "UNKNOWN"
    confidence = 999.0
    pred_id = None
    if recognizer is not None and face_roi is not None:
        try:
            pred_id, confidence = recognizer.predict(face_roi)
            confidence = float(confidence)
            if confidence <= float(unknown_threshold):
                label = id_to_name.get(int(pred_id), "UNKNOWN")
        except Exception:
            label = "UNKNOWN"
            confidence = 999.0
            pred_id = None
    return {
        "label": label if label else "UNKNOWN",
        "confidence": confidence,
        "pred_id": pred_id,
        "unknown_threshold": float(unknown_threshold),
    }

def analyze_faces(frame_bgr: np.ndarray, recognizer=None, id_to_name: Optional[dict] = None, unknown_threshold: float = 65.0):
    """Run detect -> preprocess -> predict -> threshold pipeline on a frame."""
    id_map = id_to_name or {}
    rows = []
    for item in detect_preprocess_faces(frame_bgr):
        rows.append(
            {
                "rect": item["rect"],
                "roi": item["roi"],
                **classify_face_roi(item["roi"], recognizer, id_map, unknown_threshold),
            }
        )
    return rows

def draw_face_detections(frame_bgr: np.ndarray, detections):
    """Draw bounding boxes and labels for detections on a frame copy."""
    if frame_bgr is None:
        return None
    out = frame_bgr.copy()
    for row in detections or []:
        x, y, w, h = row["rect"]
        label = str(row.get("label", "UNKNOWN") or "UNKNOWN")
        conf = float(row.get("confidence", 999.0))
        unknown = label.upper() == "UNKNOWN"
        color = (30, 30, 220) if unknown else (40, 180, 40)
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)

        if conf >= 998.0:
            text = label
        else:
            text = f"{label} {conf:.1f}"
        (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
        y2 = max(0, y - th - base - 6)
        cv2.rectangle(out, (x, y2), (x + tw + 8, y), color, -1)
        cv2.putText(
            out,
            text,
            (x + 4, y - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return out

def extract_face_roi(image_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Return grayscale 200x200 face ROI (largest face), or None."""
    rows = detect_preprocess_faces(image_bgr)
    if not rows:
        return None
    return rows[0]["roi"]

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
