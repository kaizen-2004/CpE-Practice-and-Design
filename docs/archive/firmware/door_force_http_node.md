# Door-Force Node Firmware (`door_force`) - Arduino IDE

## Board + Libraries
- Board: `ESP32C3 Dev Module` (Arduino core for ESP32 by Espressif)
- Built-in libraries used: `WiFi.h`, `HTTPClient.h`, `Wire.h`
- No third-party IMU library required (firmware uses direct LSM6DS3 register access).

## Files
- `firmware/legacy_http/door_force/door_force.ino`

## Exactly what to edit before upload
Open `firmware/legacy_http/door_force/door_force.ino` and edit these constants:

- Network/API:
  - `WIFI_SSID`
  - `WIFI_PASSWORD`
  - `SERVER_URL` (full endpoint, e.g. `http://192.168.1.50:5000/api/sensors/event`)
  - `API_KEY` (optional; leave empty to disable `X-API-KEY`)
- Identity:
  - `NODE_ID` (default `door_force`)
  - `ROOM_NAME` (default `Door Entrance Area`)
- Wiring:
  - `I2C_SDA_PIN` (default `8`)
  - `I2C_SCL_PIN` (default `9`)
  - `STATUS_LED_PIN` (default `-1`; set a pin only if you wire an external status LED)
- Detection tuning:
  - `ACCEL_DELTA_THRESHOLD_G`
  - `GYRO_THRESHOLD_DPS`
  - `FORCE_CONFIRM_SAMPLES`
  - `MIN_FORCE_EVENT_GAP_MS`
  - `CALIBRATION_SAMPLES`

## Upload steps (Arduino IDE)
1. `Tools -> Board -> ESP32 Arduino -> ESP32C3 Dev Module`
2. Select correct COM port.
3. Verify/Upload.
4. Open Serial Monitor at `115200` baud.

## Event payload format

```json
{
  "node": "door_force",
  "event": "DOOR_FORCE",
  "room": "Door Entrance Area",
  "value": 1.823,
  "unit": "score",
  "note": "delta_g=0.422 gyro_max_dps=115.4 mag_g=1.439"
}
```

The firmware also sends `DOOR_HEARTBEAT` periodically.

## How it works (short)
- Detects LSM6DS3 over I2C (`0x6A` or `0x6B`).
- Configures accel + gyro at 52 Hz.
- Calibrates baseline acceleration magnitude at boot.
- Triggers `DOOR_FORCE` when either:
  - acceleration delta exceeds threshold, or
  - gyro max exceeds threshold,
  with confirmation samples + cooldown to reduce false triggers.
- Sends heartbeat events for node visibility/health.

## Error handling + reconnect
- Wi-Fi reconnect loop retries automatically.
- IMU detection/read failures trigger periodic re-init attempts.
- Failed HTTP events are queued and retried.
- High-priority `DOOR_FORCE` can preempt non-critical pending events.

## Wiring reference
See `../hardware_wiring.md`, section:
- `3) Door-force node (door_force)`
