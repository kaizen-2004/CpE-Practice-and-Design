# smoke_node2_mqtt

MQTT firmware for `mq2_door` smoke node.

## Setup

1. Copy `firmware/mqtt/common/secrets.example.h` to `firmware/mqtt/smoke_node2_mqtt/secrets.h`.
2. Set Wi-Fi and MQTT credentials in `secrets.h`.
3. Build/upload with Arduino IDE or `arduino-cli`.

For compile-only dry runs, `secrets.h` is optional; the sketch falls back to `secrets.example.h`.
