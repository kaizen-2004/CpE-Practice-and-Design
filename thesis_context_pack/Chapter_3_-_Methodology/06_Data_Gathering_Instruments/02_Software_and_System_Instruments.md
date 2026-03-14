# Software and System Instruments

OpenCV-based facial detection and recognition module – provides identity/unknown classification along with confidence scores.  
Visual flame detection module – provides a flame/no-flame decision along with related parameters.  
Smoke sensing module – yields readings for each MQ‑2 sensor along with smoke/no‑smoke flags.  
Door-force sensing module – interprets GY‑LSM6DS3 inertial readings to generate door-force/forced-entry events.  

## Camera acquisition and transport (implementation notes)
- **Indoor camera:** USB UVC webcam acquired as a **local capture source** (e.g., `/dev/v4l/...`).  
- **Outdoor camera:** ESP32‑CAM over **HTTP** (MJPEG stream). For dashboard viewing, periodic JPEG snapshots may be pulled over HTTP.

## Sensor node communication (implementation notes)
- ESP32‑C3 nodes (`mq2_living`, `mq2_door`, `door_force`) submit readings/events via **HTTP POST + JSON** to `POST /api/sensors/event`.  
- Typical JSON fields include: `node`, `event`, optional `room`, `value`, `unit`, `ts`, and `note`.  
- **MQTT is not implemented** in this project.
