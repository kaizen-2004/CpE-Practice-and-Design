# Phase 1-5 Input/Output Signals, Parameters, and Units

This table set aligns with the current implemented baseline:
- 2 monitored areas: **Living Room**, **Door Entrance Area**
- Indoor **USB UVC** camera + outdoor **ESP32-CAM (HTTP MJPEG)**
- Sensor uplink via **HTTP POST + JSON** to `POST /api/sensors/event`
- Raspberry Pi 2 as server host, second-hand laptop as vision-processing host

## Phase 1: System Context, Scope, and Architecture Design

### Input Signals
| INPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Condo layout constraints | Number of monitored areas, entry points, camera positions | count |
| Threat profile inputs | Intruder and fire scenario categories | category |
| Hardware capability inputs | Host, camera, and node technical specs | specification sheet (N/A) |
| Platform constraint input | Server host class (Raspberry Pi 2) and vision host class (second-hand laptop) | category |
| Communication design input | Sensor-to-server protocol choice | protocol type (N/A) |

### Output Signals
| OUTPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Scope definition output | Final monitored areas (Living Room, Door Entrance Area) | count / names |
| Architecture design output | Final component topology and data flow | diagram/document (N/A) |
| Node mapping output | `mq2_living`, `mq2_door`, `door_force` assignments | node count / IDs |
| API contract output | `POST /api/sensors/event` payload schema | endpoint + fields (N/A) |
| Deployment plan output | Indoor/outdoor placement and integration plan | checklist items |

## Phase 2: Development of Core Detection Modules

### Input Signals
| INPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Face module input frames | Gray/RGB image frames for face detection/recognition | pixels |
| Flame module input frames | Indoor camera frames for flame signal extraction | pixels |
| Smoke module input signal | MQ-2 reading/value from ESP32-C3 nodes | normalized ratio / ppm-equivalent |
| Door-force module input signal | GY-LSM6DS3 motion values (accel/gyro) | g / deg/s |
| Labeled test references | Authorized/unknown, flame/non-flame, event labels | class label |

### Output Signals
| OUTPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Face decision output | `AUTHORIZED` / `UNKNOWN` + confidence score | class + score |
| Flame decision output | `FLAME_SIGNAL` detection + flame ratio | binary + ratio |
| Smoke decision output | `SMOKE_HIGH` event trigger | binary event |
| Door-force decision output | `DOOR_FORCE` event trigger | binary event |
| Module performance output | Per-module processing latency | ms |

## Phase 3: System Integration and Multi-Sensor Intelligence Layer

### Input Signals
| INPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Camera evidence input | `UNKNOWN` / `AUTHORIZED`, flame evidence from camera modules | class/event |
| Sensor event input | `SMOKE_HIGH` and `DOOR_FORCE` via HTTP POST + JSON | event + JSON fields |
| Node metadata input | `node`, `room`, `role`, last-seen status | text/timestamp |
| Fusion policy input | Fusion windows and cooldown values | seconds |
| Operating mode input | Guest mode and alert state controls | boolean/state |

### Output Signals
| OUTPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Event stream output | Normalized event records (type/source/room/ts/details) | record count |
| Fused alert output | `INTRUDER` / `FIRE`, severity, status | class + level |
| Persistent alert output | Active alert records until ACK/RESOLVED | alert count |
| Dashboard/state output | Node health, room cards, latest evidence | status fields |
| Summary output | Daily event/alert aggregates | count/day |

## Phase 4: Iterative Testing, Adjustment, and System Refinement

### Input Signals
| INPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Scenario test inputs | Normal, intruder, fire-related, nuisance runs | scenario ID / run count |
| Threshold set inputs | Unknown threshold, flame threshold, smoke/door trigger levels | score/ratio/threshold |
| Fusion rule inputs | Fire and intruder fusion windows, alert cooldowns | seconds |
| Observed error inputs | False positives, false negatives, missed detections | count |
| Usability feedback inputs | Notes on alert clarity and timing | rating/comment |

### Output Signals
| OUTPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Tuned configuration output | Updated thresholds and rule values | config version / values |
| Iteration metrics output | Accuracy, detection rate, FPR/FNR, response time | % / ms |
| Rule refinement output | Updated fusion and alert behavior definitions | versioned rule set |
| Validation output | Pass/fail outcomes per scenario | pass rate (%) |
| Iteration log output | Change history and rationale | log entries |

## Phase 5: Final Performance Evaluation and Analysis

### Input Signals
| INPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Final calibrated system input | Locked final parameter set | config version |
| Repeated trial inputs | Number of runs per event category | run count |
| Logged operational data input | Event/alert timestamps and classifications | records |
| Latency measurement input | Detection-to-alert timing samples | ms |
| User evaluation input (optional) | Alert clarity, timeliness, reliability ratings | Likert scale (1-5) |

### Output Signals
| OUTPUT SIGNALS | PARAMETER | Units |
| --- | --- | --- |
| Final detection performance output | Accuracy and detection rates by module/event type | % |
| Final error analysis output | False positives and false negatives | count / % |
| Final response-time output | Mean, median, and standard deviation latency | ms |
| Stability output | Daily/periodic event and alert behavior summary | count/day |
| User evaluation output (optional) | Mean/SD user ratings and acceptance summary | score (1-5) |
