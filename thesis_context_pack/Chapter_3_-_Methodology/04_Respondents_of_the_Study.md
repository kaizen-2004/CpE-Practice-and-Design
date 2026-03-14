# Respondents of the Study

The primary respondent of this study is the integrated prototype system itself, repeatedly tested under predefined scenarios to generate quantitative and qualitative performance data.

The evaluated prototype consists of:
- Raspberry Pi 2 host for local server services (dashboard/API/database/alerts)
- Second-hand laptop host for face-recognition and visual flame-detection processing
- Indoor USB UVC night-vision camera with IR illumination
- Outdoor ESP32-CAM night-vision camera with IR illumination
- Two ESP32-C3 smoke nodes (`mq2_living`, `mq2_door`) for Living Room and Door Entrance Area
- One ESP32-C3 door-force node (`door_force`) with GY-LSM6DS3
- Local web dashboard, alert panel, and logging components

Optional human respondents (e.g., household-member proxies, students, or faculty) may be included in final evaluation activities to rate alert clarity, timeliness, and perceived usefulness. These respondents support usability feedback and are not the primary source of technical detection performance data.
