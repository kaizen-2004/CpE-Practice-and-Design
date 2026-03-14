# Statement of the Problem

The main objective of this research is to design, construct, and evaluate a split-host real-time intruder and fire monitoring alert system, where Raspberry Pi 2 serves as the local server host and a second-hand laptop handles face-recognition and fire-detection processing.

Specifically, the study aims to:

1. Design a two-area system architecture for the Living Room and Door Entrance Area that integrates:
   - indoor USB UVC camera capture,
   - outdoor ESP32-CAM HTTP MJPEG stream input,
   - smoke sensing and door-force sensing nodes.

2. Develop the core detection modules by:
   - implementing OpenCV-based facial detection and recognition for authorized/unknown classification, and
   - implementing visual flame detection on indoor camera frames.

3. Implement integrated sensor ingestion and event handling by:
   - receiving ESP32-C3 sensor events through `POST /api/sensors/event` using HTTP POST + JSON payloads, and
   - recording events, alerts, and snapshots in the local monitoring dashboard.

4. Implement multi-sensor decision support and alerting by:
   - combining camera evidence with smoke and door-force events,
   - generating persistent local alerts and optional remote notifications.

5. Evaluate the system’s reliability and performance in terms of:
   - face identification performance,
   - fire-related detection performance (visual flame + smoke evidence),
   - door-force event detection performance, and
   - response time from event detection to alert activation.
