import os
import sqlite3
from datetime import datetime, timezone, timedelta, date as date_cls
from typing import Optional, List, Any, Dict, Tuple

# Project root is one level above this file's directory (pi/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "thesis.db")
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "snapshots")

def _utc_iso(ts: Optional[str] = None) -> str:
    """Return ISO8601 timestamp in UTC. If ts is provided, return it unchanged."""
    if ts:
        return ts
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)

def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table});")
    cols = [row[1] if isinstance(row, tuple) else row["name"] for row in cur.fetchall()]
    return column in cols

def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA foreign_keys=ON;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        source TEXT NOT NULL,
        room TEXT,
        details TEXT,
        ts TEXT NOT NULL
    );
    """)

    if not _column_exists(conn, "events", "room"):
        cur.execute("ALTER TABLE events ADD COLUMN room TEXT;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        room TEXT,
        severity INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE | ACK | RESOLVED
        ts TEXT NOT NULL,
        ack_ts TEXT,
        snapshot_path TEXT,
        details TEXT
    );
    """)

    # Snapshots are stored as relative paths under snapshots/
    cur.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        type TEXT NOT NULL,          -- FACE_UNKNOWN, FACE_AUTHORIZED, FLAME_SIGNAL, etc.
        label TEXT,                  -- UNKNOWN/AUTHORIZED/GUEST/FALSE_ALARM/etc.
        file_relpath TEXT NOT NULL,  -- e.g., "2026-01-27_intruder_unknown_001.png"
        linked_alert_id INTEGER,
        note TEXT,
        FOREIGN KEY(linked_alert_id) REFERENCES alerts(id) ON DELETE SET NULL
    );
    """)

    # Faces (UI skeleton; training optional)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS faces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        is_authorized INTEGER NOT NULL DEFAULT 1,
        created_ts TEXT NOT NULL,
        note TEXT
    );
    """)

    # A face can have multiple snapshot samples
    cur.execute("""
    CREATE TABLE IF NOT EXISTS face_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        face_id INTEGER NOT NULL,
        snapshot_id INTEGER NOT NULL,
        ts TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(face_id) REFERENCES faces(id) ON DELETE CASCADE,
        FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
        UNIQUE(face_id, snapshot_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS node_status (
        node TEXT PRIMARY KEY,
        last_seen_ts TEXT NOT NULL,
        note TEXT
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status_ts ON alerts(status, ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type_ts ON alerts(type, ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_room_ts ON events(room, ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_type ON snapshots(type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_alert ON snapshots(linked_alert_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faces_name ON faces(name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_face_samples_face ON face_samples(face_id);")

    cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('guest_mode', '0');")

    conn.commit()
    conn.close()

# -------------------- Events / Alerts --------------------
def create_event(event_type: str, source: str, details: str = "", ts: Optional[str] = None, room: str = "") -> int:
    conn = get_conn()
    cur = conn.cursor()
    ts_iso = _utc_iso(ts)
    cur.execute(
        "INSERT INTO events (type, source, room, details, ts) VALUES (?, ?, ?, ?, ?)",
        (event_type, source, room or None, details, ts_iso),
    )
    conn.commit()
    new_id = int(cur.lastrowid)
    conn.close()
    return new_id

def create_alert(
    alert_type: str,
    room: str = "",
    severity: int = 1,
    status: str = "ACTIVE",
    details: str = "",
    snapshot_path: str = "",
    ts: Optional[str] = None,
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    ts_iso = _utc_iso(ts)
    cur.execute(
        """INSERT INTO alerts (type, room, severity, status, ts, snapshot_path, details)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (alert_type, room or None, int(severity), status, ts_iso, snapshot_path or None, details),
    )
    conn.commit()
    new_id = int(cur.lastrowid)
    conn.close()
    return new_id

def ack_alert(alert_id: int, status: str = "ACK") -> bool:
    if status not in ("ACK", "RESOLVED"):
        raise ValueError("status must be 'ACK' or 'RESOLVED'")
    conn = get_conn()
    cur = conn.cursor()
    ack_ts = _utc_iso()
    cur.execute(
        "UPDATE alerts SET status = ?, ack_ts = ? WHERE id = ? AND status = 'ACTIVE'",
        (status, ack_ts, int(alert_id)),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated

def get_alert(alert_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts WHERE id = ?", (int(alert_id),))
    row = cur.fetchone()
    conn.close()
    return row

def list_active_alerts(limit: int = 200, type_filter: str = "", room_filter: str = "", q: str = "", sort: str = "newest"):
    conn = get_conn()
    cur = conn.cursor()

    sql = "SELECT * FROM alerts WHERE status = 'ACTIVE'"
    params: List[Any] = []

    if type_filter:
        sql += " AND type = ?"
        params.append(type_filter)

    if room_filter:
        sql += " AND room = ?"
        params.append(room_filter)

    if q:
        sql += " AND (IFNULL(details,'') LIKE ? OR IFNULL(room,'') LIKE ? OR type LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])

    if sort == "severity":
        sql += " ORDER BY severity DESC, ts DESC"
    else:
        sql += " ORDER BY ts DESC"

    sql += " LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_latest_event(event_type: str = "", source: str = "", room: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    sql = "SELECT * FROM events WHERE 1=1"
    params: List[Any] = []
    if event_type:
        sql += " AND type = ?"
        params.append(event_type)
    if source:
        sql += " AND source = ?"
        params.append(source)
    if room:
        sql += " AND room = ?"
        params.append(room)
    sql += " ORDER BY ts DESC LIMIT 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return row

def has_recent_event(event_type: str, source: str = "", room: str = "", within_seconds: int = 120, ts: Optional[str] = None) -> bool:
    ts_iso = _utc_iso(ts)
    center = _parse_iso(ts_iso)
    start = (center - timedelta(seconds=within_seconds)).isoformat(timespec="seconds")
    end = (center + timedelta(seconds=within_seconds)).isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.cursor()
    sql = "SELECT 1 FROM events WHERE type = ? AND ts >= ? AND ts <= ?"
    params: List[Any] = [event_type, start, end]
    if source:
        sql += " AND source = ?"
        params.append(source)
    if room:
        sql += " AND room = ?"
        params.append(room)
    sql += " LIMIT 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return row is not None

def has_recent_alert(alert_type: str, within_seconds: int = 120, ts: Optional[str] = None, room: str = "") -> bool:
    ts_iso = _utc_iso(ts)
    center = _parse_iso(ts_iso)
    start = (center - timedelta(seconds=within_seconds)).isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.cursor()
    sql = "SELECT 1 FROM alerts WHERE type = ? AND ts >= ?"
    params: List[Any] = [alert_type, start]
    if room:
        sql += " AND room = ?"
        params.append(room)
    sql += " ORDER BY ts DESC LIMIT 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return row is not None

def list_history_alerts(limit: int = 500, type_filter: str = "", room_filter: str = "", q: str = "", sort: str = "newest"):
    conn = get_conn()
    cur = conn.cursor()

    sql = "SELECT * FROM alerts WHERE status != 'ACTIVE'"
    params: List[Any] = []

    if type_filter:
        sql += " AND type = ?"
        params.append(type_filter)

    if room_filter:
        sql += " AND room = ?"
        params.append(room_filter)

    if q:
        sql += " AND (IFNULL(details,'') LIKE ? OR IFNULL(room,'') LIKE ? OR type LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])

    if sort == "severity":
        sql += " ORDER BY severity DESC, COALESCE(ack_ts, ts) DESC"
    else:
        sql += " ORDER BY COALESCE(ack_ts, ts) DESC"

    sql += " LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def distinct_alert_types():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT type FROM alerts ORDER BY type ASC;")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

def distinct_alert_rooms():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT room FROM alerts WHERE room IS NOT NULL AND room != '' ORDER BY room ASC;")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

def count_active_alerts() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM alerts WHERE status='ACTIVE';")
    c = int(cur.fetchone()["c"])
    conn.close()
    return c

# -------------------- Events --------------------
def list_recent_events(limit: int = 200, type_filter: str = "", source_filter: str = "", q: str = "", room_filter: str = ""):
    conn = get_conn()
    cur = conn.cursor()

    sql = "SELECT * FROM events WHERE 1=1"
    params: List[Any] = []

    if type_filter:
        sql += " AND type = ?"
        params.append(type_filter)

    if source_filter:
        sql += " AND source = ?"
        params.append(source_filter)

    if room_filter:
        sql += " AND room = ?"
        params.append(room_filter)

    if q:
        sql += " AND (IFNULL(details,'') LIKE ? OR type LIKE ? OR source LIKE ? OR IFNULL(room,'') LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])

    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def events_near_ts(ts: str, window_seconds: int = 600):
    """Return events within +/- window_seconds of ts."""
    center = _parse_iso(ts)
    start = (center - timedelta(seconds=window_seconds)).isoformat(timespec="seconds")
    end = (center + timedelta(seconds=window_seconds)).isoformat(timespec="seconds")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM events WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT 200;",
        (start, end),
    )
    rows = cur.fetchall()
    conn.close()
    return rows, start, end

# -------------------- Settings / Health --------------------
def set_setting(key: str, value: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
        (key, value),
    )
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return str(row["value"]) if row else default

def get_guest_mode() -> bool:
    return get_setting("guest_mode", "0") == "1"

def set_guest_mode(on: bool) -> None:
    set_setting("guest_mode", "1" if on else "0")

def update_node_seen(node: str, note: str = "", ts: Optional[str] = None) -> None:
    ts_iso = _utc_iso(ts)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO node_status(node, last_seen_ts, note)
           VALUES(?, ?, ?)
           ON CONFLICT(node) DO UPDATE SET last_seen_ts=excluded.last_seen_ts, note=excluded.note;""",
        (node, ts_iso, note or None),
    )
    conn.commit()
    conn.close()

def list_node_status():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT node, last_seen_ts, note FROM node_status ORDER BY node ASC;")
    rows = cur.fetchall()
    conn.close()
    return rows

# -------------------- Snapshots --------------------
def create_snapshot(snapshot_type: str, label: str, file_relpath: str, linked_alert_id: Optional[int] = None,
                    note: str = "", ts: Optional[str] = None) -> int:
    conn = get_conn()
    cur = conn.cursor()
    ts_iso = _utc_iso(ts)
    cur.execute(
        """INSERT INTO snapshots (ts, type, label, file_relpath, linked_alert_id, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ts_iso, snapshot_type, label or None, file_relpath, int(linked_alert_id) if linked_alert_id else None, note or None),
    )
    conn.commit()
    new_id = int(cur.lastrowid)
    conn.close()
    return new_id

def update_snapshot_label(snapshot_id: int, label: str, note: str = "") -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE snapshots SET label = ?, note = COALESCE(NULLIF(?,''), note) WHERE id = ?",
        (label or None, note, int(snapshot_id)),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok

def list_snapshots(limit: int = 120, type_filter: str = "", label_filter: str = "", q: str = ""):
    conn = get_conn()
    cur = conn.cursor()

    sql = "SELECT * FROM snapshots WHERE 1=1"
    params: List[Any] = []

    if type_filter:
        sql += " AND type = ?"
        params.append(type_filter)

    if label_filter:
        sql += " AND label = ?"
        params.append(label_filter)

    if q:
        sql += " AND (file_relpath LIKE ? OR IFNULL(note,'') LIKE ? OR IFNULL(label,'') LIKE ? OR type LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])

    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_latest_snapshot(snapshot_type: str = "", label: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    sql = "SELECT * FROM snapshots WHERE 1=1"
    params: List[Any] = []
    if snapshot_type:
        sql += " AND type = ?"
        params.append(snapshot_type)
    if label:
        sql += " AND label = ?"
        params.append(label)
    sql += " ORDER BY ts DESC LIMIT 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return row

def get_snapshot(snapshot_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM snapshots WHERE id = ?", (int(snapshot_id),))
    row = cur.fetchone()
    conn.close()
    return row

def list_snapshots_for_alert(alert_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM snapshots WHERE linked_alert_id = ? ORDER BY ts DESC LIMIT 50;", (int(alert_id),))
    rows = cur.fetchall()
    conn.close()
    return rows

def distinct_snapshot_types():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT type FROM snapshots ORDER BY type ASC;")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

def distinct_snapshot_labels():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT label FROM snapshots WHERE label IS NOT NULL AND label != '' ORDER BY label ASC;")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

# -------------------- Faces (UI skeleton) --------------------
def create_face(name: str, is_authorized: bool = True, note: str = "", ts: Optional[str] = None) -> int:
    conn = get_conn()
    cur = conn.cursor()
    ts_iso = _utc_iso(ts)
    cur.execute(
        "INSERT INTO faces (name, is_authorized, created_ts, note) VALUES (?, ?, ?, ?)",
        (name.strip(), 1 if is_authorized else 0, ts_iso, note or None),
    )
    conn.commit()
    new_id = int(cur.lastrowid)
    conn.close()
    return new_id

def list_faces():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.*,
               (SELECT COUNT(*) FROM face_samples s WHERE s.face_id = f.id) AS sample_count
        FROM faces f
        ORDER BY f.name ASC;
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_face(face_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.*,
               (SELECT COUNT(*) FROM face_samples s WHERE s.face_id = f.id) AS sample_count
        FROM faces f
        WHERE f.id = ?;
    """, (int(face_id),))
    row = cur.fetchone()
    conn.close()
    return row

def delete_face(face_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM faces WHERE id = ?", (int(face_id),))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok

def add_face_sample(face_id: int, snapshot_id: int, note: str = "", ts: Optional[str] = None) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    ts_iso = _utc_iso(ts)
    try:
        cur.execute(
            "INSERT OR IGNORE INTO face_samples (face_id, snapshot_id, ts, note) VALUES (?, ?, ?, ?)",
            (int(face_id), int(snapshot_id), ts_iso, note or None),
        )
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()
    return ok

def list_face_samples(face_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id AS sample_id, s.ts AS sample_ts, s.note AS sample_note,
               p.id AS snapshot_id, p.ts AS snapshot_ts, p.type AS snapshot_type,
               p.label AS snapshot_label, p.file_relpath AS file_relpath, p.note AS snapshot_note
        FROM face_samples s
        JOIN snapshots p ON p.id = s.snapshot_id
        WHERE s.face_id = ?
        ORDER BY s.ts DESC;
    """, (int(face_id),))
    rows = cur.fetchall()
    conn.close()
    return rows

# -------------------- Daily Summary --------------------
def _day_start_end(date_str: str) -> Tuple[str, str]:
    # date_str = 'YYYY-MM-DD' in UTC date for now
    start = datetime.fromisoformat(date_str + "T00:00:00+00:00")
    end = start + timedelta(days=1)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")

def summary_for_date(date_str: str) -> Dict[str, Any]:
    """Compute counts for a given UTC date (YYYY-MM-DD)."""
    start, end = _day_start_end(date_str)
    conn = get_conn()
    cur = conn.cursor()

    # Alerts by type/status
    cur.execute("""
        SELECT type, status, COUNT(*) AS c
        FROM alerts
        WHERE ts >= ? AND ts < ?
        GROUP BY type, status
        ORDER BY type, status;
    """, (start, end))
    alerts_rows = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT status, COUNT(*) AS c
        FROM alerts
        WHERE ts >= ? AND ts < ?
        GROUP BY status
        ORDER BY status;
    """, (start, end))
    alerts_status = [dict(r) for r in cur.fetchall()]

    # Events by type
    cur.execute("""
        SELECT type, COUNT(*) AS c
        FROM events
        WHERE ts >= ? AND ts < ?
        GROUP BY type
        ORDER BY c DESC, type ASC;
    """, (start, end))
    events_rows = [dict(r) for r in cur.fetchall()]

    # Snapshots by type/label
    cur.execute("""
        SELECT type, IFNULL(label,'') AS label, COUNT(*) AS c
        FROM snapshots
        WHERE ts >= ? AND ts < ?
        GROUP BY type, IFNULL(label,'')
        ORDER BY type ASC, label ASC;
    """, (start, end))
    snaps_rows = [dict(r) for r in cur.fetchall()]

    # Top rooms for alerts
    cur.execute("""
        SELECT IFNULL(room,'') AS room, COUNT(*) AS c
        FROM alerts
        WHERE ts >= ? AND ts < ? AND room IS NOT NULL AND room != ''
        GROUP BY room
        ORDER BY c DESC, room ASC
        LIMIT 10;
    """, (start, end))
    rooms_rows = [dict(r) for r in cur.fetchall()]

    conn.close()

    return {
        "date": date_str,
        "start": start,
        "end": end,
        "alerts_by_type_status": alerts_rows,
        "alerts_by_status": alerts_status,
        "events_by_type": events_rows,
        "snapshots_by_type_label": snaps_rows,
        "top_rooms": rooms_rows,
    }


# -------------------- Alert ↔ Snapshot helpers --------------------
def attach_snapshot_to_alert(alert_id: int, snapshot_relpath: str) -> bool:
    """Ensure alerts.snapshot_path points to snapshots/<relpath>. Returns True if updated."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE alerts SET snapshot_path = ? WHERE id = ?", (f"snapshots/{snapshot_relpath}", int(alert_id)))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok
