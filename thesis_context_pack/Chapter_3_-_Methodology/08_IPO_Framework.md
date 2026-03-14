# IPO Framework

Figure 1. IPO Framework

## Input
The development of the multi-sensor intruder-fire monitoring system required foundational knowledge in embedded systems, computer vision, and sensor integration. Core hardware/input resources included:
- Raspberry Pi host for local server services (dashboard/API/database/alerts), with optional laptop fallback for heavier vision workloads
- two night-vision camera feeds with IR illumination (indoor and outdoor ESP32-CAM streams)
- two smoke-sensing ESP32-C3 nodes (`mq2_living`, `mq2_door`)
- one door-force ESP32-C3 node (`door_force`) with GY-LSM6DS3
- MQTT topic schema and ingest path that preserves backend API compatibility (`POST /api/sensors/event`)

## Process
The process begins with defining objectives and requirements for intruder and fire detection in a two-area condo scope (Living Room and Door Entrance Area). Detection modules for face recognition, visual flame cues, smoke events, and door-force events are developed and calibrated. A fusion layer is implemented to combine visual and sensor evidence, followed by iterative scenario-based tests to refine thresholds, rules, and alert behavior.

## Output
The study produces a functional local-first prototype that classifies intruder- and fire-related events, generates alerts, and records logs/summaries through the monitoring dashboard. The resulting system demonstrates practical operation under controlled condo-like scenarios using low-cost edge components.

## Feedback
Feedback comes from repeated scenario trials and optional user evaluation. Observed misclassifications, false alarms, and response delays guide adjustments in thresholds, sensor mapping, and fusion logic. Iterative feedback cycles improve reliability, alert clarity, and overall usability.

Figure 2. Phase 1: System Context, Scope, and Architecture Design  
Researchers review literature and condo constraints, then produce architecture and deployment plans for the two-area prototype.

Figure 3. Phase 2: Development of Core Detection Modules  
Face recognition, flame detection, smoke/door-force sensing, and node firmware are implemented and calibrated on the target architecture.

Figure 4. Phase 3: System Integration and Multi-Sensor Intelligence Layer  
Modules are integrated into one pipeline, with MQTT ingestion, API-bridge compatibility, fusion logic, persistent alerts, and structured logging.

Figure 5. Phase 4: Iterative Testing, Adjustment, and System Refinement  
Scenario tests (normal, intruder, fire-related, nuisance) were repeated while tuning parameters and decision rules.

Figure 6. Phase 5: Final Performance Evaluation and Analysis  
Final repeated trials recorded event decisions, timestamps, and latency, with optional user feedback on alert clarity and timeliness.
