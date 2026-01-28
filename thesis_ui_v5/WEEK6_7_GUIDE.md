# Week 6–7 Prep: Real Snapshots + Auto-linking + LBPH Dataset

This adds:
- `pi/vision_runtime.py` — OpenCV loop to generate real events/snapshots/alerts
- `pi/vision_utils.py` — snapshot saving + face ROI export helper
- `pi/train_lbph.py` — trains LBPH model from `data/faces/<person>/` samples
- Faces page now has a **Retrain LBPH** button

## Run UI
```bash
python pi/init_db.py
python pi/app.py
```

## Run Vision Runtime (Week 6)
Second terminal:
```bash
python pi/vision_runtime.py --outdoor-url "http://OUTDOOR_IP:81/stream" --indoor-url "http://INDOOR_IP:81/stream"
```

## Auto-link snapshot ↔ alert (already done)
When UNKNOWN streak triggers INTRUDER:
- snapshot saved to `snapshots/YYYY-MM-DD/...jpg`
- alert created with `snapshot_path`
- snapshots row created with `linked_alert_id`

## Mark Authorized → Dataset + Retrain (Week 7)
1) Collect UNKNOWN snapshots (vision runtime).
2) UI → Snapshots → open → **Create Face + Link**
   - exports cropped face ROI to `data/faces/<PersonName>/...png`
3) Add 8–20 samples per person.
4) UI → Faces → **Retrain LBPH**
5) Vision runtime auto-reloads the new model.

## Notes
- LBPH requires `opencv-contrib-python` (already in requirements.txt).
- Best practice: keep samples front-facing, varied lighting, consistent ROI (200×200).
