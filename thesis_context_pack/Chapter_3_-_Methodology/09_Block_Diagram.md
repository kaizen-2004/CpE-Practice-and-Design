# Block Diagram

Figure 7. Block Diagram

The block diagram presents the current integrated architecture using a split-host setup: **Raspberry Pi 2** for server hosting (dashboard/API/database/alerts) and a **second-hand laptop** for face-recognition and visual flame-detection processing. The system monitors two areas: **Living Room** and **Door Entrance Area**.

- Indoor monitoring uses a **USB UVC webcam** with IR support (local capture source).
- Outdoor monitoring uses an **ESP32-CAM** over **HTTP MJPEG** on local Wi-Fi/LAN.
- Smoke events are provided by two ESP32-C3 nodes: `mq2_living` and `mq2_door`.
- Door-force events are provided by `door_force` (ESP32-C3 + GY-LSM6DS3).
- Sensor nodes send data via **HTTP POST + JSON** to `POST /api/sensors/event`.

The Raspberry Pi 2 host performs event logging, fusion-based alerting, and dashboard rendering, while the second-hand laptop executes vision inference. Alerts are persistent on the local interface, with optional remote delivery/access layers.
