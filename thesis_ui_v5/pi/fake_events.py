import argparse
import random
from db import init_db, create_event, list_recent_events

EVENT_TYPES = [
    ("CAM_OUTDOOR", ["AUTHORIZED", "UNKNOWN"]),
    ("CAM_INDOOR", ["AUTHORIZED", "UNKNOWN"]),
    ("SYSTEM", ["BOOT", "HEALTH_OK"]),
    ("SIM", ["FLAME_SIGNAL", "SMOKE_HIGH", "DOOR_FORCE"]),
]

def main():
    parser = argparse.ArgumentParser(description="Insert fake events into SQLite and print recent events.")
    parser.add_argument("--n", type=int, default=10, help="Number of fake events to insert")
    args = parser.parse_args()

    init_db()

    for _ in range(args.n):
        source, possible = random.choice(EVENT_TYPES)
        ev = random.choice(possible)
        details = f"simulated details for {ev}"
        new_id = create_event(ev, source, details)
        print(f"Inserted event id={new_id}: type={ev} source={source}")

    print("\n--- Recent events ---")
    for row in list_recent_events(limit=25):
        print(dict(row))

if __name__ == "__main__":
    main()
