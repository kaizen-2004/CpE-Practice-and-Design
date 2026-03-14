# Mosquitto Deployment (Raspberry Pi)

This project uses local MQTT as the primary sensor transport.

## 1) Install broker

```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
```

## 2) Install broker config

```bash
sudo cp deploy/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/thesis.conf
sudo cp deploy/mosquitto/acl /etc/mosquitto/acl
```

## 3) Create broker users

Use one user per node/service. Example:

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd thesis_ingest
sudo mosquitto_passwd /etc/mosquitto/passwd vision_runtime
sudo mosquitto_passwd /etc/mosquitto/passwd mq2_living
sudo mosquitto_passwd /etc/mosquitto/passwd mq2_door
sudo mosquitto_passwd /etc/mosquitto/passwd door_force
sudo mosquitto_passwd /etc/mosquitto/passwd cam_indoor
sudo mosquitto_passwd /etc/mosquitto/passwd cam_outdoor
```

## 4) Restart and verify

```bash
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
sudo systemctl status mosquitto
```

Publish test:

```bash
mosquitto_pub -h 127.0.0.1 -p 1883 -u mq2_living -P '<password>' \
  -t thesis/v1/events/mq2_living -m '{"v":1,"e":"SMOKE_HIGH","x":2201,"u":"adc","q":1}'
```

Subscribe test:

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 -u thesis_ingest -P '<password>' -t 'thesis/v1/#'
```
