# What you must remember is the statement of the problem of our thesis and the objectives

# Always use the OpenAI developer documentation MCP server if you need to work with the OpenAI API, ChatGPT Apps SDK, Codex,… without me having to explicitly ask.

### **Current Implementation Status (2026-03-10)**

- **Primary host:** Raspberry Pi (Flask dashboard, API, MQTT ingest service, local database, alerts).
- **Vision host:** Raspberry Pi preferred; laptop fallback remains supported for heavier vision workloads.
- **Monitored areas:** Living Room and Door Entrance Area.
- **Sensor protocol:** Backend API contract remains `POST /api/sensors/event`.
- **Transport implementation status:** Active transport is Wi-Fi MQTT (`pi/mqtt_ingest.py`); ESP-NOW and legacy HTTP firmware are archived.

### **Session Context Bootstrap (2026-03-10)**

For new coding sessions in this repository, read context in this order:

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/context/CURRENT_STATUS.md`
4. `README.md`

For firmware and sensor transport tasks, additionally read:

5. `docs/instructions/transport/mqtt_quick_start.md`
6. `docs/instructions/transport/mqtt_deployment.md`

For deployment/autostart tasks on Raspberry Pi, additionally read:

7. `docs/instructions/deployment/pi_systemd_autostart.md`

If the user says to "use docs directory" or similar, treat `docs/` as the primary project context source and follow the read order above.

### **Title**

**Real-Time Intruder and Fire Monitoring Alert System Using IoT Facial Recognition with Night-Vision Camera**

---

### **1. Main Objective**

The main objective of this research is to **design, construct, and evaluate a Raspberry Pi–based real-time intruder and fire monitoring alert system** that uses **night-vision cameras for OpenCV-based facial recognition and visual flame detection**, together with **indoor smoke sensors and a door motion/force sensor**, to provide timely and persistent warnings to the user.

### **2. Specific Objectives**

Specifically, the study aims to:

1. **Design** the overall **system architecture** that integrates the **Raspberry Pi 4**, an **outdoor face-level night-vision camera**, a **single indoor night-vision camera**, **multiple indoor smoke sensors** (via an analog-to-digital converter), and a **door motion/force sensor** for condominium-based intruder and fire-related monitoring.
2. **Develop** the core detection algorithms by
   - implementing an **OpenCV-based facial detection and recognition pipeline** on the Raspberry Pi for identifying authorized versus unknown individuals, and
   - creating a **visual flame detection algorithm** that analyzes indoor camera footage to infer possible fire events, in combination with smoke sensor readings.
3. **Implement** the integrated system by
   - constructing the necessary **hardware and software interfaces** between the Raspberry Pi, the cameras, the smoke sensors, and the door sensor, and
   - enabling **automatic logging and classification** of intruder-related and fire-related events based on multi-sensor fusion.
4. **Generate** a **summary of event and identification statistics** over a given period (e.g., daily), including
   - the number of **recognized authorized faces**,
   - the number of **unrecognized or suspicious detections**, and
   - the number of **detected fire-related visual and smoke events**.
5. **Evaluate** the system’s overall **reliability and performance** in terms of
   - **face identification accuracy**,
   - **fire-related detection performance**, including **visual flame and smoke-sensor false-positive and false-negative rates**, and
   - **system response time** from event occurrence to alert activation.

---

### **Keywords**

Raspberry Pi, Facial Recognition, Flame Detection, Real-Time Detection, Night-Vision Camera
