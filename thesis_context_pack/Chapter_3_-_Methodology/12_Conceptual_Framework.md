# Conceptual Framework (Updated Markdown Version)

Figure X. Updated Conceptual Framework for the Real-Time Intruder and Fire Monitoring Alert System

This conceptual framework follows the five-phase engineering flow used in Chapter 3 and aligns with the current implementation baseline: Raspberry Pi as the primary host, MQTT-based sensor transport, and dual-area monitoring (Living Room and Door Entrance Area).

## Phase 1: System Architecture and Component Design

1. Define the system scope by identifying target threats: unauthorized persons (intruders) and fire-related events.
2. Design the integrated architecture using Raspberry Pi (primary host), indoor and outdoor night-vision ESP32-CAM units, two smoke-sensor nodes, and one door-force sensor node.
3. Plan physical deployment, node placement, monitored zones, and notification recipients.

**Phase 1 Output:** Finalized architecture, deployment map, and node/area assignments.

## Phase 2: Core Algorithm and Subsystem Development

4. Develop and benchmark the face pipeline (OpenCV face detection + LBPH recognition) for authorized-vs-unknown classification.
5. Create the visual flame detection algorithm for indoor camera input.
6. Construct and calibrate smoke and door-force sensor subsystems, including firmware event publishing.
7. Test subsystem-level detection behavior and latency under controlled conditions.

**Phase 2 Output:** Validated module-level detection pipelines and calibrated sensor subsystems.

## Phase 3: System Integration and Multi-Sensor Intelligence Layer

8. Implement multi-criteria fire verification that requires both visual flame evidence and smoke evidence within the configured fusion window.
9. Integrate ESP32 nodes and Raspberry Pi services through MQTT (`publish -> broker -> ingest bridge -> POST /api/sensors/event`).
10. Develop the Python-based monitoring interface (Flask backend + dashboard) for event logs, alerts, and face/sensor management workflows.
11. Construct the notification framework for persistent mobile alerts and operator acknowledgment handling.

**Phase 3 Output:** Fully integrated local-first monitoring stack with fusion logic, persistent alerts, and event logging.

## Phase 4: System Deployment and Operational Testing

12. Deploy the integrated stack in the target condo-like environment for real-time operation.
13. Send automated mobile notifications to designated recipients upon verified threat detection.
14. Activate and validate end-to-end alert operation (detection, classification, logging, notification, acknowledgment).

**Phase 4 Output:** Operational deployment with validated alert delivery and monitoring behavior.

## Phase 5: Performance Evaluation and Analysis

15. Evaluate reliability and performance using face-identification accuracy, fire-detection false-positive/false-negative behavior, and end-to-end alert latency.
16. Analyze consolidated logs and daily summaries to assess system effectiveness over repeated scenarios.
17. Document the final performance statistics and prepare the formal evaluation report.

**Phase 5 Output:** Finalized performance results and thesis-ready evaluation documentation.

## End-to-End Conceptual Flow

`Phase 1 (Design) -> Phase 2 (Module Development) -> Phase 3 (Integration + Fusion) -> Phase 4 (Deployment + Operational Testing) -> Phase 5 (Evaluation + Documentation)`
