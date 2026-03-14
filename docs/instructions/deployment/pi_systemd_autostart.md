# Pi Autostart with systemd (MQTT Architecture)

This setup prepares auto-start for:

- Flask app (`pi/app.py`)
- MQTT ingest bridge (`pi/mqtt_ingest.py`)
- Optional vision runtime (`pi/vision_runtime.py`)

This document is for deployment machine setup. Services are generated then installed.

## Files

- `deploy/systemd/templates/thesis-app.service.tmpl`
- `deploy/systemd/templates/thesis-mqtt-ingest.service.tmpl`
- `deploy/systemd/templates/thesis-vision.service.tmpl`
- `deploy/systemd/templates/thesis-stack.target.tmpl`
- `deploy/systemd/thesis.env.example`
- `deploy/systemd/prepare_units.sh`
- `deploy/systemd/install_units.sh`

## 1) Prepare Units (on deployment Pi)

From project root:

```bash
bash deploy/systemd/prepare_units.sh \
  --project-root /home/pi/projects/CpE-Practice-and-Design \
  --run-user pi \
  --python-bin /home/pi/projects/CpE-Practice-and-Design/.venv/bin/python3
```

Output:

- `deploy/systemd/thesis.env`
- `deploy/systemd/generated/thesis-app.service`
- `deploy/systemd/generated/thesis-mqtt-ingest.service`
- `deploy/systemd/generated/thesis-vision.service`
- `deploy/systemd/generated/thesis-stack.target`

## 2) Review Environment

Edit `deploy/systemd/thesis.env` if needed:

- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`
- `MQTT_BROKER_USERNAME`
- `MQTT_BROKER_PASSWORD`
- `MQTT_TOPIC_ROOT`
- `SENSOR_EVENT_URL`
- `SENSOR_API_KEY`
- `VISION_EVENT_SINK`

## 3) Install Services

```bash
sudo bash deploy/systemd/install_units.sh \
  --generated-dir deploy/systemd/generated \
  --enable-stack \
  --enable-vision \
  --start-now
```

Use `--enable-vision` only when vision runtime should run on Pi.

## 4) Verify

```bash
systemctl status thesis-app.service thesis-mqtt-ingest.service thesis-stack.target
systemctl status thesis-vision.service
journalctl -u thesis-app.service -f
journalctl -u thesis-mqtt-ingest.service -f
```

## 5) Notes

- Unit files load both:
  - `<project-root>/.env` (optional)
  - `<project-root>/deploy/systemd/thesis.env` (required)
- Mosquitto must be installed and running on the Pi.
