import argparse
import random
from db import init_db, create_alert, list_active_alerts

ALERT_TYPES = ["INTRUDER", "FIRE", "DOOR_FORCE"]
ROOMS = ["Door Entrance Area", "Living Room"]

def main():
    parser = argparse.ArgumentParser(description="Insert fake ACTIVE alerts into SQLite and print active alerts.")
    parser.add_argument("--n", type=int, default=5, help="Number of fake alerts to insert")
    args = parser.parse_args()

    init_db()

    for _ in range(args.n):
        alert_type = random.choice(ALERT_TYPES)
        room = random.choice(ROOMS)
        severity = random.randint(1, 3)  # 1=low, 2=med, 3=high
        details = f"simulated {alert_type} in {room}"
        new_id = create_alert(alert_type, room=room, severity=severity, status="ACTIVE", details=details)
        print(f"Inserted alert id={new_id}: type={alert_type} room={room} severity={severity}")

    print("\n--- ACTIVE alerts ---")
    for row in list_active_alerts(limit=50):
        print(dict(row))

if __name__ == "__main__":
    main()
