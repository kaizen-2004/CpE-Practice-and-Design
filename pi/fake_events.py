import argparse
import random
from db import init_db, create_event, list_recent_events
from config import (
    EVENT_AUTHORIZED,
    EVENT_UNKNOWN,
    EVENT_FLAME_SIGNAL,
    EVENT_SMOKE_HIGH,
    EVENT_DOOR_FORCE,
)

EVENT_SOURCES = [
    ("CAM_OUTDOOR", "Door Entrance Area", [EVENT_AUTHORIZED, EVENT_UNKNOWN]),
    ("CAM_INDOOR", "Living Room", [EVENT_AUTHORIZED, EVENT_UNKNOWN, EVENT_FLAME_SIGNAL]),
    ("mq2_living", "Living Room", [EVENT_SMOKE_HIGH]),
    ("mq2_door", "Door Entrance Area", [EVENT_SMOKE_HIGH]),
    ("door_force", "Door Entrance Area", [EVENT_DOOR_FORCE]),
]

def main():
    parser = argparse.ArgumentParser(description="Insert fake events into SQLite and print recent events.")
    parser.add_argument("--n", type=int, default=10, help="Number of fake events to insert")
    args = parser.parse_args()

    init_db()

    for _ in range(args.n):
        source, room, possible = random.choice(EVENT_SOURCES)
        ev = random.choice(possible)
        details = f"simulated details for {ev}"
        new_id = create_event(ev, source, details, room=room)
        print(f"Inserted event id={new_id}: type={ev} source={source}")

    print("\n--- Recent events ---")
    for row in list_recent_events(limit=25):
        print(dict(row))

if __name__ == "__main__":
    main()
