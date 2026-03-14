# Phase 3: System Integration and Multi-Sensor Intelligence Layer

The tested modules are combined to build a single continuous prototype that uses facial recognition, visual flame detection, smoke readings, and door-force readings to detect and classify events as normal, intruder-related, or fire-related. Integration tests are carried out initially in the lab and then in the condo-like environment to ascertain that sensor events result in correct classifications, persistent alerts, and recorded log entries. System-generated logs and daily summaries are gathered.

In the integrated prototype, sensor nodes transmit readings/events to the server using **HTTP POST + JSON** to a unified endpoint (e.g., `POST /api/sensors/event`). The indoor camera is acquired via a local USB UVC capture source, while the outdoor ESP32-CAM provides frames over HTTP (MJPEG stream; dashboard may display periodic JPEG snapshots) on the same Wi‑Fi/LAN.
