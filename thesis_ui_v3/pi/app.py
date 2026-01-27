from flask import Flask, redirect, render_template, request, url_for, flash, send_from_directory, abort
from db import (
    init_db,
    list_active_alerts,
    list_history_alerts,
    list_recent_events,
    ack_alert,
    get_guest_mode,
    set_guest_mode,
    distinct_alert_types,
    distinct_alert_rooms,
    count_active_alerts,
    list_node_status,
    update_node_seen,
    get_alert,
    events_near_ts,
    list_snapshots,
    get_snapshot,
    list_snapshots_for_alert,
    distinct_snapshot_types,
    distinct_snapshot_labels,
    SNAPSHOT_DIR,
)

app = Flask(__name__)
app.secret_key = "dev-only-change-me"  # change later for real deployments

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
    return render_template("snapshot_details.html", snap=snap)

@app.get("/files/snapshots/<path:filename>")
def serve_snapshot(filename: str):
    # Serve only from snapshots directory
    return send_from_directory(SNAPSHOT_DIR, filename, as_attachment=False)

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

# Convenience route to seed node health during NO-hardware phase (remove later)
@app.post("/seed/health")
def seed_health():
    update_node_seen("door_node", note="simulated")
    update_node_seen("mq2_kitchen", note="simulated")
    update_node_seen("cam_outdoor", note="simulated")
    update_node_seen("cam_indoor", note="simulated")
    flash("Seeded simulated node health entries.", "success")
    return redirect(url_for("health"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
