# Session Q&A Log

Date: 2026-03-03

## 1) Can I use LoRa instead of ESP32 connected via HTTP?
**Answer:** Partially. LoRa can replace low-data sensor uplink, but it is not practical for ESP32-CAM real-time video streaming. Keep camera on Wi-Fi/HTTP; LoRa is viable for smoke/door-force events via a gateway bridge to the same API.

## 2) Is LoRa the path of less resistance than ESP32?
**Answer:** No. For most builds, ESP32 over Wi-Fi (HTTP/MQTT) is simpler and faster to finish. LoRa adds radio constraints, packet design, retries/ACK, and gateway complexity.

## 3) Even if I can change code, is LoRa easier?
**Answer:** Still generally no for this system. LoRa is not a drop-in replacement for camera streaming. It can be used for sensor events, but integration is still more complex than Wi-Fi HTTP.

## 4) Are smoke and door-force nodes better on LoRa than ESP32 Wi-Fi?
**Answer:** Not automatically. If range is short and Wi‑Fi is stable, ESP32 Wi‑Fi is easier and more reliable operationally. LoRa helps mostly in long-range/low-power cases.

## 5) If I remove ESP32 and ESP32-CAM, what replacements can I use?
**Answer:**
- For camera: use USB UVC camera, Pi camera, or IP camera over HTTP/RTSP.
- For sensors: use non-ESP32 LoRa nodes plus a gateway that forwards events to backend API.
- Do not use LoRa for live video transport.

## 6) Best low-headache option?
**Answer:** ESP32/ESP32-CAM over local Wi‑Fi with HTTP-based integration.

## 7) Can I get no-bias answer not based on current code?
**Answer:** Yes. In general, Wi‑Fi + HTTP/MQTT is less headache than LoRa for camera + sensor systems. Use LoRa only when long-range/low-power constraints dominate.

## 8) Will there be no hardware constraints? Specific specs?
**Answer:** There are always constraints: host CPU/RAM, camera FPS/resolution, stable power rails, sensor electrical requirements, and network quality. Weak power and unstable Wi‑Fi are common failure points.

## 9) If outdoor camera is ESP32-CAM, what specs should we lock?
**Answer:** AI Thinker ESP32-CAM with PSRAM, regulated 5V/2A supply, IP65 enclosure, IR lighting, 2.4GHz Wi‑Fi with strong RSSI, and conservative stream profile (QVGA/VGA, ~8–12 fps).

## 10) For thesis demo, do we need a router for HTTP addressing?
**Answer:** Internet is not required, but a local AP/router is strongly recommended. Alternatives (phone/laptop hotspot) can work but are less stable for demo conditions.

## 11) What if indoor camera is thermal or infrared?
**Answer:**
- NoIR/IR camera is better for face and scene detail at night.
- Thermal is better for hotspot/heat cues but lower detail and often lower frame rate; weak for identity tasks.
- Best practical setup: NoIR as main camera, thermal as optional secondary fire cue.

## 12) What is the optimal setup given fire false positives and face constraints?
**Answer:**
- Use stable hardware/network profile and conservative CV settings.
- Reduce fire false positives with: room-aware fusion, motion-gated flame logic, stronger hard-negative dataset, stricter blob/hot-core thresholds, and temporal gating.
- Calibrate LBPH unknown threshold from validation data rather than fixed guess values.

---

If needed, this file can be expanded into a thesis appendix format (Issue -> Cause -> Fix -> Result table).
