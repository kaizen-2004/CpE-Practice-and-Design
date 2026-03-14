  Use this order:

  1. door_force end-to-end

  - prove door_force -> gateway -> pi/serial_ingest.py -> Flask -> dashboard
  - confirm DOOR_HEARTBEAT appears in Activity
  - confirm real movement triggers DOOR_FORCE
  - confirm alert appears and can be acknowledged/resolved

  2. smoke_node1 and smoke_node2

  - flash both with the same final ESP-NOW pattern
  - confirm SMOKE_HIGH reaches the backend
  - confirm smoke events appear on dashboard/activity

  3. cameras

  4. vision events

  - cameras on
  - Flask on
  - Telegram notifications working
  - run one intruder-style test and one fire-style test
