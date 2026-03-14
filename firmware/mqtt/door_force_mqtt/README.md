# door_force_mqtt

MQTT firmware for `door_force` IMU node.

## Setup

1. Copy `firmware/mqtt/common/secrets.example.h` to `firmware/mqtt/door_force_mqtt/secrets.h`.
2. Set Wi-Fi and MQTT credentials in `secrets.h`.
3. Verify I2C pins for your ESP32-C3 board (default SDA=8, SCL=9).

For compile-only dry runs, `secrets.h` is optional; the sketch falls back to `secrets.example.h`.
