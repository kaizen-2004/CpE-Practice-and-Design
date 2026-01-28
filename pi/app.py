from flask import Flask, redirect, render_template, request, url_for, flash, send_from_directory, abort, Response
import csv
import io
from datetime import datetime, timezone, timedelta
import os
import sys
import subprocess

from db import (
    init_db,
    # alerts
    list_active_alerts,
    list_history_alerts,
    list_recent_events,
    ack_alert,
    get_guest_mode,
    set_guest_mode,
    distinct_alert_types,
    distinct_alert_rooms,
    count_active_alerts,
    get_alert,
    events_near_ts,
    # health
    list_node_status,
    update_node_seen,
    # snapshots
    list_snapshots,
    get_snapshot,
    list_snapshots_for_alert,
    distinct_snapshot_types,
    distinct_snapshot_labels,
    update_snapshot_label,
    SNAPSHOT_DIR,
    # faces
    list_faces,
    get_face,
    create_face,
    delete_face,
    add_face_sample,
    list_face_samples,
    # summary
    summary_for_date,
)
from vision_utils import export_face_sample_from_snapshot

app = Flask(__name__)
app.secret_key = "dev-only-change-me"  # change later for real deployments

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "faces")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")


init_db()

@app.context_processor
def inject_globals():
    return {
        "guest_mode": get_guest_mode(),
        "active_alert_count": count_active_alerts(),
    }

@app.get("/")
def home():
    return redirect(url_for("dashboard"))

# ---- Dashboard / Alerts ----
@app.get("/dashboard")
def dashboard():
    type_filter = request.args.get("type", "").strip()
    room_filter = request.args.get("room", "").strip()
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "newest").strip()

    alerts = list_active_alerts(type_filter=type_filter, room_filter=room_filter, q=q, sort=sort)
    types = distinct_alert_types()
    rooms = distinct_alert_rooms()
    return render_template(
        "dashboard.html",
        alerts=alerts,
        types=types,
        rooms=rooms,
        type_filter=type_filter,
        room_filter=room_filter,
        q=q,
        sort=sort,
    )

@app.get("/alert/<int:alert_id>")
def alert_details(alert_id: int):
    alert = get_alert(alert_id)
    if not alert:
        abort(404)
    snaps = list_snapshots_for_alert(alert_id)
    near_events, start, end = events_near_ts(alert["ts"], window_seconds=600)
    return render_template("alert_details.html", alert=alert, snapshots=snaps, near_events=near_events, win_start=start, win_end=end)

@app.post("/ack/<int:alert_id>")
def ack(alert_id: int):
    status = request.form.get("status", "ACK").upper().strip()
    if status not in ("ACK", "RESOLVED"):
        status = "ACK"

    ok = ack_alert(alert_id, status=status)
    if ok:
        flash(f"Alert #{alert_id} set to {status}.", "success")
    else:
        flash(f"Alert #{alert_id} was not ACTIVE (nothing changed).", "warning")
    return redirect(request.referrer or url_for("dashboard"))

@app.get("/history")
def history():
    type_filter = request.args.get("type", "").strip()
    room_filter = request.args.get("room", "").strip()
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "newest").strip()

    alerts = list_history_alerts(type_filter=type_filter, room_filter=room_filter, q=q, sort=sort)
    types = distinct_alert_types()
    rooms = distinct_alert_rooms()
    return render_template("history.html", alerts=alerts, types=types, rooms=rooms,
                           type_filter=type_filter, room_filter=room_filter, q=q, sort=sort)

# ---- Events ----
@app.get("/events")
def events():
    type_filter = request.args.get("type", "").strip()
    source_filter = request.args.get("source", "").strip()
    q = request.args.get("q", "").strip()
    rows = list_recent_events(type_filter=type_filter, source_filter=source_filter, q=q)
    return render_template("events.html", events=rows, type_filter=type_filter, source_filter=source_filter, q=q)

# ---- Snapshots ----
@app.get("/snapshots")
def snapshots():
    type_filter = request.args.get("type", "").strip()
    label_filter = request.args.get("label", "").strip()
    q = request.args.get("q", "").strip()

    snaps = list_snapshots(type_filter=type_filter, label_filter=label_filter, q=q)
    types = distinct_snapshot_types()
    labels = distinct_snapshot_labels()
    return render_template("snapshots.html", snapshots=snaps, types=types, labels=labels,
                           type_filter=type_filter, label_filter=label_filter, q=q)

@app.get("/snapshot/<int:snapshot_id>")
def snapshot_details(snapshot_id: int):
    snap = get_snapshot(snapshot_id)
    if not snap:
        abort(404)
    faces = list_faces()
    return render_template("snapshot_details.html", snap=snap, faces=faces)

@app.post("/snapshot/<int:snapshot_id>/label")
def snapshot_set_label(snapshot_id: int):
    label = request.form.get("label", "").strip()
    note = request.form.get("note", "").strip()
    if not label:
        flash("Please choose a label.", "warning")
        return redirect(url_for("snapshot_details", snapshot_id=snapshot_id))
    ok = update_snapshot_label(snapshot_id, label=label, note=note)
    if ok:
        flash(f"Snapshot #{snapshot_id} labeled as {label}.", "success")
    else:
        flash("Snapshot not found.", "warning")
    return redirect(url_for("snapshot_details", snapshot_id=snapshot_id))

@app.post("/faces/from_snapshot/<int:snapshot_id>")
def create_face_from_snapshot(snapshot_id: int):
    name = request.form.get("name", "").strip()
    note = request.form.get("note", "").strip()
    if not name:
        flash("Face name is required.", "warning")
        return redirect(url_for("snapshot_details", snapshot_id=snapshot_id))

    face_id = create_face(name=name, is_authorized=True, note=note)
    add_face_sample(face_id, snapshot_id, note="added from snapshot")

    # Export a cropped face ROI sample into the LBPH dataset folder
    try:
        os.makedirs(DATASET_DIR, exist_ok=True)
        person_dir = os.path.join(DATASET_DIR, name.strip())
        from db import get_snapshot, SNAPSHOT_DIR
        snap = get_snapshot(snapshot_id)
        if snap:
            snap_abs = os.path.join(SNAPSHOT_DIR, snap["file_relpath"])
            out_name = f"{snapshot_id}_{snap['ts'].replace(':','-')}.png"
            out_path = export_face_sample_from_snapshot(snap_abs, person_dir, out_name)
            if out_path is None:
                flash("⚠️ Face ROI not found in snapshot (saved face record, but dataset sample not created).", "warning")
    except Exception:
        flash("⚠️ Could not export dataset sample (you can still add samples later).", "warning")


    # Optional convenience: also label the snapshot as AUTHORIZED
    update_snapshot_label(snapshot_id, label="AUTHORIZED")

    flash(f"Created face '{name}' and linked Snapshot #{snapshot_id}.", "success")
    return redirect(url_for("face_details", face_id=face_id))

@app.post("/faces/<int:face_id>/add_sample")
def add_sample_to_face(face_id: int):
    snapshot_id = request.form.get("snapshot_id", "").strip()
    if not snapshot_id.isdigit():
        flash("Invalid snapshot id.", "warning")
        return redirect(url_for("face_details", face_id=face_id))
    ok = add_face_sample(face_id, int(snapshot_id), note="added via UI")

    # Also export ROI sample into dataset folder under this face name
    try:
        face = get_face(face_id)
        from db import get_snapshot, SNAPSHOT_DIR
        snap = get_snapshot(int(snapshot_id))
        if face and snap:
            person_dir = os.path.join(DATASET_DIR, face["name"].strip())
            snap_abs = os.path.join(SNAPSHOT_DIR, snap["file_relpath"])
            out_name = f"{snapshot_id}_{snap['ts'].replace(':','-')}.png"
            export_face_sample_from_snapshot(snap_abs, person_dir, out_name)
    except Exception:
        pass

    if ok:
        flash(f"Added Snapshot #{snapshot_id} as a sample.", "success")
    else:
        flash("That snapshot was already linked or does not exist.", "warning")
    return redirect(url_for("face_details", face_id=face_id))

@app.get("/files/snapshots/<path:filename>")
def serve_snapshot(filename: str):
    return send_from_directory(SNAPSHOT_DIR, filename, as_attachment=False)

# ---- Faces ----
@app.get("/faces")
def faces():
    rows = list_faces()
    return render_template("faces.html", faces=rows)

@app.get("/faces/<int:face_id>")
def face_details(face_id: int):
    face = get_face(face_id)
    if not face:
        abort(404)
    samples = list_face_samples(face_id)
    return render_template("face_details.html", face=face, samples=samples)

@app.post("/faces/new")
def faces_new():
    name = request.form.get("name", "").strip()
    note = request.form.get("note", "").strip()
    if not name:
        flash("Name is required.", "warning")
        return redirect(url_for("faces"))
    face_id = create_face(name=name, is_authorized=True, note=note)
    flash(f"Created face '{name}'.", "success")
    return redirect(url_for("face_details", face_id=face_id))

@app.post("/faces/<int:face_id>/delete")
def faces_delete(face_id: int):
    ok = delete_face(face_id)
    flash("Face deleted." if ok else "Face not found.", "success" if ok else "warning")
    return redirect(url_for("faces"))

# ---- Health / Settings ----
@app.post("/settings/guest_mode")
def toggle_guest_mode():
    current = get_guest_mode()
    set_guest_mode(not current)
    flash(f"Guest Mode is now {'ON' if not current else 'OFF'}.", "success")
    return redirect(request.referrer or url_for("dashboard"))

@app.get("/health")
def health():
    nodes = list_node_status()
    return render_template("health.html", nodes=nodes)

@app.post("/seed/health")
def seed_health():
    update_node_seen("door_node", note="simulated")
    update_node_seen("mq2_kitchen", note="simulated")
    update_node_seen("cam_outdoor", note="simulated")
    update_node_seen("cam_indoor", note="simulated")
    flash("Seeded simulated node health entries.", "success")
    return redirect(url_for("health"))

# ---- Daily Summary ----
def _today_utc_date_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()

@app.get("/summary")
def summary():
    date_str = request.args.get("date", "").strip() or _today_utc_date_str()
    data = summary_for_date(date_str)

    # build a simple date picker list: last 14 days in UTC
    today = datetime.now(timezone.utc).date()
    date_options = [(today - timedelta(days=i)).isoformat() for i in range(0, 14)]
    return render_template("summary.html", data=data, date_str=date_str, date_options=date_options)

@app.get("/summary.csv")
def summary_csv():
    date_str = request.args.get("date", "").strip() or _today_utc_date_str()
    data = summary_for_date(date_str)

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", data["date"]])
    w.writerow(["window_start", data["start"]])
    w.writerow(["window_end", data["end"]])
    w.writerow([])

    w.writerow(["ALERTS by type/status"])
    w.writerow(["type", "status", "count"])
    for r in data["alerts_by_type_status"]:
        w.writerow([r["type"], r["status"], r["c"]])
    w.writerow([])

    w.writerow(["ALERTS by status"])
    w.writerow(["status", "count"])
    for r in data["alerts_by_status"]:
        w.writerow([r["status"], r["c"]])
    w.writerow([])

    w.writerow(["EVENTS by type"])
    w.writerow(["type", "count"])
    for r in data["events_by_type"]:
        w.writerow([r["type"], r["c"]])
    w.writerow([])

    w.writerow(["SNAPSHOTS by type/label"])
    w.writerow(["type", "label", "count"])
    for r in data["snapshots_by_type_label"]:
        w.writerow([r["type"], r["label"], r["c"]])
    w.writerow([])

    w.writerow(["TOP ROOMS (alerts)"])
    w.writerow(["room", "count"])
    for r in data["top_rooms"]:
        w.writerow([r["room"], r["c"]])

    resp = Response(out.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="summary_{date_str}.csv"'
    return resp

@app.get("/summary.html")
def summary_html_export():
    date_str = request.args.get("date", "").strip() or _today_utc_date_str()
    data = summary_for_date(date_str)
    # Minimal standalone HTML export using the same template but export mode
    html = render_template("summary_export.html", data=data, date_str=date_str)
    resp = Response(html, mimetype="text/html; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="summary_{date_str}.html"'
    return resp


@app.post("/faces/retrain")
def faces_retrain():
    """
    Train LBPH model from data/faces/<person> samples.
    Runs as a subprocess so errors don't crash Flask.
    """
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "pi", "train_lbph.py")]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            flash("✅ LBPH retraining complete. Vision runtime will auto-reload the new model.", "success")
        else:
            msg = (res.stdout + "\n" + res.stderr).strip()
            flash("❌ Retrain failed:\n" + (msg[:900] + ("…" if len(msg) > 900 else "")), "warning")
    except Exception as e:
        flash(f"❌ Retrain error: {e}", "warning")

    return redirect(url_for("faces"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
