# Smoke Node 2 Firmware (`mq2_door`) - Arduino IDE

## Board + Libraries
- Board: `ESP32C3 Dev Module` (Arduino core for ESP32 by Espressif)
- Built-in libraries used: `WiFi.h`, `HTTPClient.h`
- No extra library is required.

## Files
- `firmware/legacy_http/smoke_node2/smoke_node2.ino`

## Exactly what to edit before upload
Open `firmware/legacy_http/smoke_node2/smoke_node2.ino` and edit these constants:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `SERVER_URL` (full endpoint, e.g. `http://192.168.1.50:5000/api/sensors/event`)
- `API_KEY` (optional; leave empty string to disable `X-API-KEY` header)
- `NODE_ID` (default `mq2_door`)
- `ROOM_NAME` (default `Door Entrance Area`)
- `MQ2_ADC_PIN` (default `0`)
- `STATUS_LED_PIN` if your board LED pin differs (`-1` disables LED)
- Thresholds/timing:
  - `ADC_HIGH_THRESHOLD`
  - `ADC_CLEAR_THRESHOLD`
  - `HIGH_CONFIRM_SAMPLES`
  - `CLEAR_CONFIRM_SAMPLES`
  - `HEARTBEAT_INTERVAL_MS`

## Upload steps (Arduino IDE)
1. `Tools -> Board -> ESP32 Arduino -> ESP32C3 Dev Module`
2. Select correct COM port.
3. Verify/Upload.
4. Open Serial Monitor at `115200` baud.

## Event payload format
Firmware posts JSON to your unified endpoint:

```json
{
  "node": "mq2_door",
  "event": "SMOKE_HIGH",
  "room": "Door Entrance Area",
  "value": 2310,
  "unit": "adc_raw",
  "note": "threshold_crossed"
}
```

## How it works (short)
- Reads MQ-2 analog output every second.
- Uses threshold + hysteresis + confirmation counts to reduce noise.
- Sends `SMOKE_HIGH` when sustained high smoke is detected.
- Sends `SMOKE_NORMAL` when readings return below clear threshold.
- Sends periodic `SMOKE_HEARTBEAT` to keep node health visible.

## Error handling + reconnect
- Wi-Fi reconnect loop retries every `WIFI_RETRY_INTERVAL_MS`.
- Failed HTTP posts are queued and retried every `HTTP_RETRY_INTERVAL_MS`.
- Critical events (`SMOKE_HIGH`) can preempt non-critical queued events.

## Important power/safety note
MQ-2 heater draws significant current. Power the sensor from a stable `5V` supply and share GND with ESP32-C3. Ensure the ADC pin never exceeds `3.3V`.
