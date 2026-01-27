# Thesis UI v3 (Snapshots + Alert Details + Better UX)

Adds (requested):
- `/snapshots` page (thumbnail grid + filters)
- `/snapshot/<id>` full view page
- `/alert/<id>` alert details page (snapshot + linked snapshots + nearby events)
- Better UX:
  - Auto-refresh (Dashboard only) via UX menu
  - Sound on new alerts (optional) via UX menu
  - Severity sort option

## Setup (fresh folder)
```bash
python -m venv .venv
# activate venv, then:
pip install -r requirements.txt
python pi/init_db.py
python pi/fake_events.py --n 20
python pi/fake_snapshots.py --n 12 --link-alerts
python pi/fake_alerts.py --n 5
python pi/app.py
```

Open:
- http://127.0.0.1:5000/dashboard
- http://127.0.0.1:5000/snapshots
- click any alert -> Details
- click any snapshot -> full view

## Upgrade from UI v2
Copy/replace into your existing project:
- `pi/app.py`
- `pi/db.py`
- `pi/templates/*`
- add `pi/static/app.css`
- add `pi/fake_snapshots.py`
Then run:
```bash
python pi/init_db.py
python pi/fake_snapshots.py --n 12 --link-alerts
python pi/app.py
```
