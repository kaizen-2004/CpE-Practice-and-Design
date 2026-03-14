# Scope and Delimitation

This research covers the conceptualization, development, and controlled evaluation of a local-first intruder and fire monitoring prototype for a condo-like setting.

The implemented system scope is limited to **two monitored areas**:
- **Living Room**
- **Door Entrance Area**

The prototype uses two night-vision camera feeds supported by IR illumination:
- an **indoor USB UVC wired webcam** connected directly to the host, and
- an **outdoor ESP32-CAM** transmitting **MJPEG over HTTP** on the local Wi-Fi/LAN.

Sensor coverage includes:
- two ESP32-C3 smoke nodes (`mq2_living`, `mq2_door`) using MQ-2 sensing, and
- one ESP32-C3 door-force node (`door_force`) using a GY-LSM6DS3 inertial sensor.

Sensor-to-server communication is implemented through **HTTP POST + JSON** to `POST /api/sensors/event` (MQTT is not used in the implementation).

The implemented architecture is split across two hosts: Raspberry Pi 2 serves as the central controller/dashboard/API/database server, while a second-hand laptop executes face-recognition and visual flame-detection runtime processing.

Performance evaluation focuses on controlled scenarios: normal activity, simulated intruder behavior, smoke/flame-related conditions (within safety limits), and nuisance cases such as steam or non-threatening motion. Metrics include face identification performance, fire-related detection performance, door-force detection behavior, and response time.

The investigation is limited to a single-unit prototype and does not include multi-unit deployment, direct integration with external emergency response agencies, or long-term field deployment in occupied condominiums. Remote access and notification channels (e.g., Tailscale and Telegram) are treated as optional layers; core detection, logging, and local dashboard operation remain the primary implementation focus.
