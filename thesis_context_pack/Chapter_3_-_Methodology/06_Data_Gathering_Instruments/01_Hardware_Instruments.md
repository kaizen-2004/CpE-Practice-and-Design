# Hardware/Instruments

Raspberry Pi 2 Linux host - local dashboard/API/database/alert server.  
Second-hand laptop - host for face-recognition and visual flame-detection processing.  
Indoor USB UVC night-vision camera + IR illumination – supplies frames for indoor monitoring and visual flame detection.  
Outdoor ESP32-CAM + IR illumination – records facial images at the door and transmits frames over HTTP on the local Wi‑Fi/LAN.  
Two (2) MQ-2 smoke sensing points – one per monitored area (Living Room and Door Entrance Area).  
Two (2) ESP32-C3 smoke nodes (`mq2_living`, `mq2_door`) – post smoke readings/events to the server.  
GY‑LSM6DS3 + one (1) ESP32-C3 door-force node (`door_force`) – identifies forced-entry motion events.  
Local HDMI display / dashboard – used for alerts and monitoring.
