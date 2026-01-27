import argparse
import os
import random
from datetime import datetime, timezone
import cv2
import numpy as np

from db import init_db, create_snapshot, create_alert, SNAPSHOT_DIR

TYPES = [
    ("FACE_UNKNOWN", "UNKNOWN"),
    ("FACE_AUTHORIZED", "AUTHORIZED"),
    ("FLAME_SIGNAL", "FLAME"),
]
ROOMS = ["Door", "Living Area", "Kitchen"]

def make_image(text: str, subtitle: str) -> np.ndarray:
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # simple gradient background
    for y in range(img.shape[0]):
        val = int(30 + (y / img.shape[0]) * 50)
        img[y, :, :] = (val, val, val)
    cv2.rectangle(img, (30, 30), (610, 450), (80, 80, 80), 2)
    cv2.putText(img, text, (60, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (240, 240, 240), 3, cv2.LINE_AA)
    cv2.putText(img, subtitle, (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2, cv2.LINE_AA)
    cv2.putText(img, "SIMULATED SNAPSHOT", (60, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2, cv2.LINE_AA)
    return img

def main():
    parser = argparse.ArgumentParser(description="Generate simulated snapshot images + DB rows (NO hardware).")
    parser.add_argument("--n", type=int, default=8, help="Number of snapshots to generate")
    parser.add_argument("--link-alerts", action="store_true", help="Create linked ACTIVE alerts for some snapshots")
    args = parser.parse_args()

    init_db()
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    for i in range(args.n):
        stype, label = random.choice(TYPES)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fname = ts.replace(":", "-") + f"_{stype.lower()}_{i:03d}.png"
        relpath = fname
        fullpath = os.path.join(SNAPSHOT_DIR, relpath)

        room = random.choice(ROOMS)
        title = stype.replace("_", " ")
        subtitle = f"Room: {room} | Label: {label}"
        img = make_image(title, subtitle)
        cv2.imwrite(fullpath, img)

        linked_alert_id = None
        if args.link_alerts and random.random() < 0.6:
            # create an alert and link the snapshot to it
            alert_type = "INTRUDER" if stype.startswith("FACE") and label == "UNKNOWN" else ("FIRE" if stype == "FLAME_SIGNAL" else "DOOR_FORCE")
            linked_alert_id = create_alert(alert_type, room=room, severity=random.randint(1,3), status="ACTIVE",
                                          details=f"auto-linked sim alert for {stype}", snapshot_path=f"snapshots/{relpath}", ts=ts)

        create_snapshot(stype, label, relpath, linked_alert_id=linked_alert_id, note="simulated", ts=ts)
        print(f"✅ snapshot saved: {relpath} (type={stype}, label={label}, linked_alert={linked_alert_id})")

if __name__ == "__main__":
    main()
