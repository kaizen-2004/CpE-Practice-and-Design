# Research Setting

The study was conducted in two primary settings:

1. **University Laboratory / Workshop**  
This setting was used for literature review, architecture design, programming, and bench-top validation of the core modules. Hardware assembly and controlled tests followed a split-host design where Raspberry Pi 2 handled local server hosting and a second-hand laptop handled face/fire vision processing.

2. **Condo-like / Simulated Condominium Environment**  
This setting was used for integrated system deployment and scenario-based testing. The implementation scope covered two monitored areas only:
- **Living Room**
- **Door Entrance Area**

In this setup, the indoor USB UVC camera monitored interior activity and flame-related visual cues, while the outdoor ESP32-CAM monitored the entrance area over HTTP MJPEG. Two smoke nodes (`mq2_living`, `mq2_door`) and one door-force node (`door_force` with GY-LSM6DS3) sent event data to the host through HTTP POST + JSON (`POST /api/sensors/event`).
