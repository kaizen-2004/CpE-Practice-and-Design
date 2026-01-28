import os
import json
from pathlib import Path
from datetime import datetime, timezone
import cv2

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "faces")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "lbph.yml")
LABELS_PATH = os.path.join(MODELS_DIR, "labels.json")
FACE_SIZE = (200, 200)

def ensure_dirs():
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

def load_dataset():
    images, labels = [], []
    names = sorted([p.name for p in Path(DATASET_DIR).iterdir() if p.is_dir()])
    name_to_id = {name: i for i, name in enumerate(names)}
    id_to_name = {i: name for name, i in name_to_id.items()}

    for name in names:
        person_dir = Path(DATASET_DIR) / name
        for img_path in person_dir.glob("*"):
            if img_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
                continue
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            if img.shape[:2] != (FACE_SIZE[1], FACE_SIZE[0]):
                img = cv2.resize(img, FACE_SIZE, interpolation=cv2.INTER_AREA)
            images.append(img)
            labels.append(name_to_id[name])
    return images, labels, id_to_name

def main():
    ensure_dirs()
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
    except Exception as e:
        raise SystemExit(
            "❌ cv2.face not available. Install opencv-contrib-python.\n"
            "pip install opencv-contrib-python\n\n"
            f"Original error: {e}"
        )

    images, labels, id_to_name = load_dataset()
    if len(images) < 2 or len(set(labels)) < 1:
        raise SystemExit("❌ Not enough training data. Add samples to data/faces/<person>/ first.")

    recognizer.train(images, labels)
    recognizer.save(MODEL_PATH)

    meta = {
        "trained_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id_to_name": {str(k): v for k, v in id_to_name.items()},
        "image_count": len(images),
        "person_count": len(set(labels)),
        "face_size": list(FACE_SIZE),
    }
    with open(LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print("✅ Trained LBPH model")
    print(f"   model:  {MODEL_PATH}")
    print(f"   labels: {LABELS_PATH}")
    print(f"   people: {meta['person_count']} | images: {meta['image_count']}")

if __name__ == "__main__":
    main()
