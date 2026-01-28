# Thesis UI v4 — Snapshots tagging + Faces manager + Daily Summary (NO hardware friendly)

This package implements ALL 3 requested items in one go:
1) Snapshots actions:
   - Tag snapshot as AUTHORIZED / UNKNOWN / GUEST / FALSE_ALARM
   - Optional note
2) Faces page skeleton:
   - /faces list + create
   - create face from snapshot (1 click flow)
   - face details page showing sample snapshots
   - link any snapshot as a sample by ID
3) Daily Summary page:
   - /summary with date picker (last 14 days UTC)
   - export CSV: /summary.csv?date=YYYY-MM-DD
   - export HTML: /summary.html?date=YYYY-MM-DD

## Run (fresh folder)
```bash
python -m venv .venv
# activate venv...
pip install -r requirements.txt

python pi/init_db.py
python pi/fake_events.py --n 20
python pi/fake_snapshots.py --n 18 --link-alerts
python pi/fake_alerts.py --n 6
python pi/app.py
```

Open:
- http://127.0.0.1:5000/dashboard
- http://127.0.0.1:5000/snapshots  (open a snapshot to tag + add to faces)
- http://127.0.0.1:5000/faces
- http://127.0.0.1:5000/summary

## Upgrade from v3
Copy/replace into your existing project:
- `pi/app.py`
- `pi/db.py`  (adds faces + face_samples + summary helpers)
- `pi/templates/*`
- `pi/static/app.css`
- add `pi/fake_snapshots.py` (if you don't already have it)
Then run:
```bash
python pi/init_db.py
python pi/fake_snapshots.py --n 12 --link-alerts
python pi/app.py
```
