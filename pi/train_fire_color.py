import json
import os
from datetime import datetime, timezone
from pathlib import Path

import cv2

from fire_utils import flame_ratio

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "fire")
FLAME_DIR = os.path.join(DATASET_DIR, "flame")
NON_FLAME_DIR = os.path.join(DATASET_DIR, "non_flame")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "fire_color.json")


def _image_files(folder: str):
    if not os.path.isdir(folder):
        return []
    out = []
    for p in Path(folder).iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            out.append(p)
    return sorted(out)


def _ratios(files):
    ratios = []
    for path in files:
        img = cv2.imread(str(path))
        if img is None:
            continue
        ratios.append(flame_ratio(img))
    return ratios


def main():
    os.makedirs(FLAME_DIR, exist_ok=True)
    os.makedirs(NON_FLAME_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

    flame_files = _image_files(FLAME_DIR)
    non_flame_files = _image_files(NON_FLAME_DIR)
    if len(flame_files) < 5 or len(non_flame_files) < 5:
        raise SystemExit(
            "Need at least 5 flame and 5 non_flame images in data/fire/ before training."
        )

    flame_vals = _ratios(flame_files)
    non_vals = _ratios(non_flame_files)
    if not flame_vals or not non_vals:
        raise SystemExit("Could not read enough valid images from dataset.")

    flame_mean = float(sum(flame_vals) / len(flame_vals))
    non_mean = float(sum(non_vals) / len(non_vals))
    raw_threshold = (flame_mean + non_mean) / 2.0
    ratio_threshold = max(0.002, min(0.7, raw_threshold))

    model = {
        "trained_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": "hsv_ratio_baseline",
        "ratio_threshold": round(ratio_threshold, 6),
        "flame_count": len(flame_vals),
        "non_flame_count": len(non_vals),
        "flame_mean_ratio": round(flame_mean, 6),
        "non_flame_mean_ratio": round(non_mean, 6),
    }

    with open(MODEL_PATH, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)

    print("Fire model trained")
    print(f"model: {MODEL_PATH}")
    print(f"flame images: {model['flame_count']} | non_flame images: {model['non_flame_count']}")
    print(f"ratio threshold: {model['ratio_threshold']}")


if __name__ == "__main__":
    main()
