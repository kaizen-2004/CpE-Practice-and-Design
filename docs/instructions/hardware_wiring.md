# Condo Monitoring Circuits

This document defines wiring assumptions for all five devices.

## Global power + wiring rules
- Use a **common ground (GND)** across ESP boards and sensor modules.
- Keep ESP32 logic pins at **3.3V max**.
- Use separate/stable power for high-current modules (MQ-2 heater, ESP32-CAM).
- Keep analog and power wires short to reduce noise.

---

## 1) Smoke sensor node 1 (`mq2_living`)
Device: ESP32-C3 + MQ-2 module

### Pin mapping
| MQ-2 module pin | ESP32-C3 pin | Notes |
| --- | --- | --- |
| `VCC` | `5V` | MQ-2 heater requires 5V supply |
| `GND` | `GND` | Common ground |
| `AO` | `GPIO0` (ADC) | Main smoke reading input |
| `DO` | Not used (optional `GPIO1`) | Optional digital threshold output |

### Power notes
- MQ-2 can draw notable heater current; avoid powering from weak USB hubs.
- If AO can exceed 3.3V on your module, add a voltage divider before ESP ADC.

### Recommended divider (if needed)
- `AO -> 10k -> ADC pin`
- `ADC pin -> 20k -> GND`
- This scales ~0-5V to ~0-3.3V.

---

## 2) Smoke sensor node 2 (`mq2_door`)
Device: ESP32-C3 + MQ-2 module

### Pin mapping
| MQ-2 module pin | ESP32-C3 pin | Notes |
| --- | --- | --- |
| `VCC` | `5V` | MQ-2 heater requires 5V supply |
| `GND` | `GND` | Common ground |
| `AO` | `GPIO0` (ADC) | Main smoke reading input |
| `DO` | Not used (optional `GPIO1`) | Optional digital threshold output |

### Power notes
- Same electrical notes as smoke node 1.
- Calibrate threshold separately per location.

---

## 3) Door-force node (`door_force`)
Device: ESP32-C3 + GY-LSM6DS3 (IMU)

### Pin mapping (I2C)
| GY-LSM6DS3 pin | ESP32-C3 pin | Notes |
| --- | --- | --- |
| `VCC` | `3V3` | Use 3.3V logic supply |
| `GND` | `GND` | Common ground |
| `SDA` | `GPIO8` | I2C data |
| `SCL` | `GPIO9` | I2C clock |
| `INT1` | Optional `GPIO10` | Optional interrupt pin |

### Required resistors/modules
- Most breakout boards already include I2C pull-ups.
- If not, add `4.7k` pull-up from SDA to 3V3 and SCL to 3V3.

### Power notes
- Keep IMU on 3.3V only.
- Avoid long unshielded I2C wires.

---

## 4) Outdoor camera node (`cam_outdoor`)
Device: ESP32-CAM (AI Thinker) streaming HTTP MJPEG/snapshots

### Firmware camera pin map (AI Thinker ESP32-CAM)
These pins are fixed by the module and used in firmware:

| Signal | GPIO |
| --- | --- |
| `PWDN` | 32 |
| `XCLK` | 0 |
| `SIOD` | 26 |
| `SIOC` | 27 |
| `Y2..Y9` | 5, 18, 19, 21, 36, 39, 34, 35 |
| `VSYNC` | 25 |
| `HREF` | 23 |
| `PCLK` | 22 |
| Flash LED | 4 |

### Runtime wiring
| ESP32-CAM pin | Connection | Notes |
| --- | --- | --- |
| `5V` | Stable 5V supply (>=2A recommended) | Camera + Wi-Fi spikes require strong supply |
| `GND` | GND | Common ground |

### Programming wiring (USB-to-TTL adapter)
| USB-TTL pin | ESP32-CAM pin | Notes |
| --- | --- | --- |
| `TX` | `U0R` | Cross-connect serial |
| `RX` | `U0T` | Cross-connect serial |
| `GND` | `GND` | Common ground |
| `5V` | `5V` | Power during flashing |
| `GPIO0` -> `GND` | (jumper only for flashing) | Enter flash mode |

### Flashing sequence
1. Connect `GPIO0` to `GND`.
2. Reset/power-cycle board.
3. Upload firmware.
4. Remove `GPIO0`-`GND` jumper.
5. Reset/power-cycle to run normally.

### Power notes
- Brownout resets are common with weak supplies. Use short thick power leads.

---

## 5) Indoor camera node (`cam_indoor`)
Device: ESP32-CAM (AI Thinker) streaming HTTP MJPEG/snapshots

Indoor camera wiring is identical to outdoor ESP32-CAM wiring:

- Same AI Thinker pin map
- Same 5V supply quality requirements
- Same USB-to-TTL flashing method (`GPIO0 -> GND` for flash mode)

Deploy indoor camera at Living Room coverage and outdoor camera at Door Entrance Area.

---

## Optional protection modules
- 5V buck converter (if powering from battery/12V source).
- TVS diode/fuse for noisy power sources.
- RC filter on MQ-2 analog output if readings are unstable.
