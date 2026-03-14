# Thesis Timeline / Gantt Chart

**Project Title:** Real-time Intruder and Fire Monitoring Alert System using IoT Facial Recognition with Night Vision Camera

## Week-to-Month Map
| Month | Week # |
| --- | --- |
| February | 1-2 |
| March | 3-6 |
| April | 7-11 |
| May | 12-15 |
| June | 16-18 |

## Project Week to Actual Calendar Week Map
Assumptions:
- **Project Week 1 = Calendar Week 7**
- Date ranges use **ISO calendar weeks (Monday-Sunday), Year 2026**

| Project Week | Actual Calendar Week | Actual Date Range (2026) |
| --- | --- | --- |
| 1 | 7 | Feb 9-Feb 15 |
| 2 | 8 | Feb 16-Feb 22 |
| 3 | 9 | Feb 23-Mar 1 |
| 4 | 10 | Mar 2-Mar 8 |
| 5 | 11 | Mar 9-Mar 15 |
| 6 | 12 | Mar 16-Mar 22 |
| 7 | 13 | Mar 23-Mar 29 |
| 8 | 14 | Mar 30-Apr 5 |
| 9 | 15 | Apr 6-Apr 12 |
| 10 | 16 | Apr 13-Apr 19 |
| 11 | 17 | Apr 20-Apr 26 |
| 12 | 18 | Apr 27-May 3 |
| 13 | 19 | May 4-May 10 |
| 14 | 20 | May 11-May 17 |
| 15 | 21 | May 18-May 24 |
| 16 | 22 | May 25-May 31 |
| 17 | 23 | Jun 1-Jun 7 |
| 18 | 24 | Jun 8-Jun 14 |

## Activity Schedule (Gantt-Style, Week Range)
| #   | Activity                                                                                 | Start Project Week | End Project Week | Start Actual Week | End Actual Week | Actual Date Range (2026) |
| --- | ---------------------------------------------------------------------------------------- | ------------------ | ---------------- | ----------------- | --------------- | ------------------------ |
| 1   | ~~Flask UI baseline (Dashboard/History/ACK/snapshots) - Laptop~~                         | 1                  | 2                | 7                 | 8               | Feb 9-Feb 22             |
| 2   | ~~Database schema + event/alert engine baseline - Laptop~~                               | 1                  | 3                | 7                 | 9               | Feb 9-Mar 1              |
| 3   | ~~Flask UI baseline (Dashboard/History/ACK/snapshots) - Laptop~~                         | 2                  | 3                | 8                 | 9               | Feb 16-Mar 1             |
| 4   | REST endpoints + security (API key, logging, rate limits) - Server                       | 3                  | 4                | 9                 | 10              | Feb 23-Mar 8             |
| 5   | ~~Vision runtime skeleton (capture loop, frame-skip, queue -> DB) - Laptop~~             | 4                  | 5                | 10                | 11              | Mar 2-Mar 15             |
| 6   | ~~Face detect + LBPH training + "Retrain" UI~~                                           | 4                  | 5                | 10                | 11              | Mar 2-Mar 15             |
| 7   | ~~Raspberry Pi primary host setup (Flask/API/DB/alerts + MQTT ingest)~~                  | 5                  | 6                | 11                | 12              | Mar 9-Mar 22             |
| 8   | ~~Vision host fallback setup on second-hand laptop (face/fire runtime)~~                 | 6                  | 7                | 12                | 13              | Mar 16-Mar 29            |
| 9   | ~~ESP32-C3 MQ-2 Node 1 and 2 firmware + MQTT integration~~                               | 5                  | 7                | 11                | 13              | Mar 9-Mar 29             |
| 10  | ~~Door-force IMU node (GY-LSM6DS3) firmware + MQTT integration to `/api/sensors/event`~~ | 6                  | 8                | 12                | 14              | Mar 16-Apr 5             |
| 11  | ~~ESP32-CAM indoor+outdoor: stream stability + IR baseline validation~~                  | 6                  | 8                | 12                | 14              | Mar 16-Apr 5             |
| 12  | ~~Flame detection baseline (video simulation -> indoor cam)~~                            | 8                  | 9                | 14                | 15              | Mar 30-Apr 12            |
| 13  | ~~Fusion logic (FIRE + INTRUDER scoring windows)~~                                       | 9                  | 10               | 15                | 16              | Apr 6-Apr 19             |
| 14  | Full system integration + performance tuning (CPU, FPS, ROI) + system enclosure          | 9                  | 11               | 15                | 17              | Apr 6-Apr 26             |
| 15  | Remote access (Tailscale) + Telegram notifications (optional shows)                      | 10                 | 11               | 16                | 17              | Apr 13-Apr 26            |
| 16  | Testing and evaluation (module + scenario, metrics, latency)                             | 11                 | 13               | 17                | 19              | Apr 20-May 10            |
| 17  | Thesis writing (Ch 1-5, diagrams, results, tables)                                       | 2                  | 14               | 8                 | 20              | Feb 16-May 17            |
| 18  | Final polish (bugs, UI cleanup, demo script, rehearsal)                                  | 14                 | 15               | 20                | 21              | May 11-May 24            |
| 19  | Submission + presentation + defense (working prototype)                                  | 15                 | 16               | 21                | 22              | May 18-May 31            |

## Progress Update (As of March 12, 2026)
- **Current project week:** Week 5 (Calendar Week 11, Mar 9-Mar 15, 2026)
- **Estimated overall completion:** **79%** (implementation-first progress snapshot)
- **Legend:** Done = complete, In Progress = partially complete, Not Started = no implementation yet

| # | Activity | Status | Est. % Complete | Progress Notes |
| --- | --- | --- | --- | --- |
| 1 | ~~Flask UI baseline (Dashboard/History/ACK/snapshots) - Laptop~~ | Done | 100% | Core pages and ACK flow are implemented in Flask templates/routes. |
| 2 | ~~Database schema + event/alert engine baseline - Laptop~~ | Done | 100% | SQLite schema and alert/event operations are implemented in `pi/db.py`. |
| 3 | ~~Flask UI baseline (Dashboard/History/ACK/snapshots) - Laptop~~ | Done | 100% | UI routes and pages exist and are integrated. |
| 4 | REST endpoints + security (API key, logging, rate limits) - Server | In Progress | 80% | `POST /api/sensors/event` + API-key guard and logging are operational; rate-limit hardening remains pending. |
| 5 | ~~Vision runtime skeleton (capture loop, frame-skip, queue -> DB) - Laptop~~ | Done | 100% | `pi/vision_runtime.py` capture/process loop writes events and snapshots. |
| 6 | ~~Face detect + LBPH training + "Retrain" UI~~ | Done | 100% | Face capture/training routes, LBPH retraining, and live overlays are operational. |
| 7 | ~~Raspberry Pi primary host setup (Flask/API/DB/alerts + MQTT ingest)~~ | Done | 100% | Raspberry Pi is now the primary host for API, ingest, dashboard, DB, and alerts. |
| 8 | ~~Vision host fallback setup on second-hand laptop (face/fire runtime)~~ | Done | 100% | Laptop fallback mode remains supported for heavier vision loads. |
| 9 | ~~ESP32-C3 MQ-2 Node 1 and 2 firmware + MQTT integration~~ | Done | 100% | Active MQTT smoke firmware is deployed under `firmware/mqtt/`. |
| 10 | ~~Door-force IMU node (GY-LSM6DS3) firmware + MQTT integration to `/api/sensors/event`~~ | Done | 100% | `door_force_mqtt` is active; events are bridged via ingest to the same backend endpoint contract. |
| 11 | ~~ESP32-CAM indoor+outdoor: stream stability + IR baseline validation~~ | Done | 100% | Indoor/outdoor camera nodes are integrated for monitored areas with baseline night operation. |
| 12 | ~~Flame detection baseline (video simulation -> indoor cam)~~ | Done | 100% | Indoor flame detection pipeline is active and fused with smoke events. |
| 13 | ~~Fusion logic (FIRE + INTRUDER scoring windows)~~ | Done | 100% | Fusion windows/cooldowns are implemented in `pi/fusion.py`. |
| 14 | Full system integration + performance tuning (CPU, FPS, ROI) + system enclosure | In Progress | 72% | Integration is operational on the Pi-first topology; performance tuning and enclosure finalization remain. |
| 15 | Remote access (Tailscale) + Telegram notifications (optional shows) | In Progress | 85% | Telegram alert pipeline is implemented; remote-access finalization remains optional/in progress. |
| 16 | Testing and evaluation (module + scenario, metrics, latency) | In Progress | 50% | Metrics and summary export exist; formal repeated scenario runs and statistical treatment are ongoing. |
| 17 | Thesis writing (Ch 1-5, diagrams, results, tables) | In Progress | 65% | Writing is ongoing with implementation context updated; results/discussion sections remain in progress. |
| 18 | Final polish (bugs, UI cleanup, demo script, rehearsal) | Not Started | 0% | Scheduled for later weeks. |
| 19 | Submission + presentation + defense (working prototype) | Not Started | 0% | Scheduled near defense period. |

### Milestone Progress (As of March 12, 2026)
| Project Week # | Milestone | Actual Date Range (2026) | Status |
| --- | --- | --- | --- |
| 15 | Final Oral Defense | May 18-May 24 | Not yet due |
| 16 | Revisions on Project and Documents | May 25-May 31 | Not yet due |
| 17 | Submission of Final Revisions and Prototype | Jun 1-Jun 7 | Not yet due |
| 18 | Submission and Releasing of Final Grade | Jun 8-Jun 14 | Not yet due |

## Milestones
| Project Week # | Actual Week # | Milestone | Actual Date Range (2026) |
| --- | --- | --- | --- |
| 15 | 21 | Final Oral Defense | May 18-May 24 |
| 16 | 22 | Revisions on Project and Documents | May 25-May 31 |
| 17 | 23 | Submission of Final Revisions and Prototype | Jun 1-Jun 7 |
| 18 | 24 | Submission and Releasing of Final Grade | Jun 8-Jun 14 |

## Team
- **Group Leader:** Luisito Bernardo
- **Members:** Dwight Baines Camposano, Judemar Silmar, Steve Villa
- **Adviser:** Prof. Minerva Zoleta

---
*Note: This is a Markdown reconstruction of the provided chart. If you want, I can also generate a second version using a Mermaid `gantt` block for presentation slides and docs.*
