#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <math.h>

#include "../common/mqtt_payload.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

/*
  Door-Force Node (ESP32-C3 + GY-LSM6DS3) via MQTT
  Node ID: door_force
*/

const char *NODE_ID = "door_force";
const char *ROOM_NAME = "Door Entrance Area";

static const int I2C_SDA_PIN = 8;
static const int I2C_SCL_PIN = 9;
static const int STATUS_LED_PIN = -1;
static const bool STATUS_LED_ACTIVE_LOW = true;

static const uint32_t SAMPLE_INTERVAL_MS = 50;
static const uint32_t MIN_FORCE_EVENT_GAP_MS = 10000;
static const uint32_t EVENT_RETRY_INTERVAL_MS = 5000;
static const uint32_t IMU_REINIT_INTERVAL_MS = 5000;
static const uint32_t WIFI_RETRY_INTERVAL_MS = 15000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
static const uint32_t MQTT_RETRY_INTERVAL_MS = 5000;
static const uint16_t MQTT_KEEPALIVE_SECONDS = 120;
static const wifi_power_t WIFI_TX_POWER_LEVEL = WIFI_POWER_8_5dBm;

static const uint16_t CALIBRATION_SAMPLES = 100;
static const uint8_t FORCE_CONFIRM_SAMPLES = 2;
static const float ACCEL_DELTA_THRESHOLD_G = 0.35f;
static const float GYRO_THRESHOLD_DPS = 90.0f;
static const float BASELINE_ALPHA = 0.01f;
static const float BASELINE_UPDATE_MAX_DELTA_G = 0.12f;
static const float BASELINE_UPDATE_MAX_GYRO_DPS = 25.0f;

static const uint8_t REG_WHO_AM_I = 0x0F;
static const uint8_t REG_CTRL1_XL = 0x10;
static const uint8_t REG_CTRL2_G = 0x11;
static const uint8_t REG_CTRL3_C = 0x12;
static const uint8_t REG_OUTX_L_G = 0x22;
static const uint8_t WHO_AM_I_VALUE = 0x69;

struct ImuSample {
  float ax = 0.0f;
  float ay = 0.0f;
  float az = 0.0f;
  float gx = 0.0f;
  float gy = 0.0f;
  float gz = 0.0f;
};

struct PendingEvent {
  bool active = false;
  String event;
  float value = 0.0f;
  String unit;
  String note;
  uint32_t nextAttemptMs = 0;
};

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

char topicEvent[80];
char topicStatus[80];
char mqttClientId[48];

PendingEvent pendingEvent;

bool imuReady = false;
bool calibrated = false;
uint8_t imuAddress = 0;
float baselineMagG = 1.0f;
float calibSumMag = 0.0f;
uint16_t calibCount = 0;
uint8_t confirmCount = 0;
uint32_t eventSeq = 0;

uint32_t lastSampleMs = 0;
uint32_t lastForceEventMs = 0;
uint32_t lastImuInitAttemptMs = 0;
uint32_t lastWiFiAttemptMs = 0;
uint32_t lastWiFiBeginMs = 0;
uint32_t lastMqttAttemptMs = 0;
bool imuStateStatusSent = false;
bool lastImuReadyStatus = false;
bool lastCalibratedStatus = false;

void setStatusLed(bool on) {
  if (STATUS_LED_PIN < 0) return;
  int level = on ? HIGH : LOW;
  if (STATUS_LED_ACTIVE_LOW) level = on ? LOW : HIGH;
  digitalWrite(STATUS_LED_PIN, level);
}

void updateLedPattern() {
  if (!imuReady) {
    bool blinkOn = ((millis() / 120) % 2) == 0;
    setStatusLed(blinkOn);
    return;
  }
  if (mqttClient.connected()) {
    setStatusLed(true);
    return;
  }
  bool blinkOn = ((millis() / 300) % 2) == 0;
  setStatusLed(blinkOn);
}

void beginWiFiConnection() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  WiFi.setTxPower(WIFI_TX_POWER_LEVEL);
  lastWiFiBeginMs = millis();
}

void ensureWiFi() {
  wl_status_t st = WiFi.status();
  if (st == WL_CONNECTED) return;
  uint32_t now = millis();
  if ((uint32_t)(now - lastWiFiBeginMs) < WIFI_CONNECT_TIMEOUT_MS) return;
  if ((uint32_t)(now - lastWiFiAttemptMs) < WIFI_RETRY_INTERVAL_MS) return;
  if (st == WL_DISCONNECTED || st == WL_CONNECT_FAILED || st == WL_NO_SSID_AVAIL) {
    lastWiFiAttemptMs = now;
    WiFi.disconnect();
    delay(200);
    beginWiFiConnection();
    Serial.printf("[WiFi] reconnecting ssid=%s status=%d\n", WIFI_SSID, (int)st);
  }
}

bool publishStatus(bool online, const char *note) {
  if (!mqttClient.connected()) return false;
  char payload[200];
  mqttBuildStatusPayload(payload, sizeof(payload), online ? 1 : 0, WiFi.RSSI(), mqttNextSeq(eventSeq), note);
  return mqttClient.publish(topicStatus, payload, true);
}

bool publishEvent(const String &eventName, float value, const String &unit, const String &note) {
  if (!mqttClient.connected()) return false;
  char payload[260];
  mqttBuildEventPayload(
      payload,
      sizeof(payload),
      eventName.c_str(),
      value,
      unit.c_str(),
      mqttNextSeq(eventSeq),
      note.c_str(),
      ROOM_NAME);
  return mqttClient.publish(topicEvent, payload, false);
}

void ensureMqtt() {
  if (mqttClient.connected() || WiFi.status() != WL_CONNECTED) return;
  uint32_t now = millis();
  if ((uint32_t)(now - lastMqttAttemptMs) < MQTT_RETRY_INTERVAL_MS) return;
  lastMqttAttemptMs = now;

  char willPayload[120];
  mqttBuildStatusPayload(willPayload, sizeof(willPayload), 0, 0, 0, "offline");

  mqttClient.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
  mqttClient.setKeepAlive(MQTT_KEEPALIVE_SECONDS);
  bool ok = mqttClient.connect(
      mqttClientId,
      MQTT_USERNAME,
      MQTT_PASSWORD,
      topicStatus,
      2,
      true,
      willPayload);

  if (ok) {
    publishStatus(true, "boot");
    imuStateStatusSent = false;
    Serial.println("[MQTT] connected");
  } else {
    Serial.printf("[MQTT] connect failed rc=%d\n", mqttClient.state());
  }
}

void publishImuStateStatusIfChanged() {
  if (!mqttClient.connected()) return;
  if (imuStateStatusSent && imuReady == lastImuReadyStatus && calibrated == lastCalibratedStatus) return;

  String note = String("imu=") + (imuReady ? "ok" : "offline") +
                " cal=" + (calibrated ? "yes" : "no") +
                " base=" + String(baselineMagG, 3);
  publishStatus(true, note.c_str());
  imuStateStatusSent = true;
  lastImuReadyStatus = imuReady;
  lastCalibratedStatus = calibrated;
}

void queuePending(const String &eventName, float value, const String &unit, const String &note) {
  pendingEvent.active = true;
  pendingEvent.event = eventName;
  pendingEvent.value = value;
  pendingEvent.unit = unit;
  pendingEvent.note = note;
  pendingEvent.nextAttemptMs = 0;
}

void emitEvent(const String &eventName, float value, const String &unit, const String &note, bool highPriority) {
  if (pendingEvent.active && !highPriority) return;
  if (pendingEvent.active && highPriority) pendingEvent.active = false;

  if (!publishEvent(eventName, value, unit, note)) {
    queuePending(eventName, value, unit, note);
  } else {
    Serial.printf("[MQTT] sent %s value=%.3f\n", eventName.c_str(), value);
  }
}

void processPendingEvent() {
  if (!pendingEvent.active) return;
  uint32_t now = millis();
  if (now < pendingEvent.nextAttemptMs) return;

  if (publishEvent(pendingEvent.event, pendingEvent.value, pendingEvent.unit, pendingEvent.note)) {
    pendingEvent.active = false;
    Serial.printf("[MQTT] retry sent %s\n", pendingEvent.event.c_str());
    return;
  }
  pendingEvent.nextAttemptMs = now + EVENT_RETRY_INTERVAL_MS;
}

bool i2cReadBytes(uint8_t addr, uint8_t reg, uint8_t *out, size_t len) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  size_t got = Wire.requestFrom((int)addr, (int)len);
  if (got != len) return false;
  for (size_t i = 0; i < len; ++i) out[i] = Wire.read();
  return true;
}

bool i2cWriteByte(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool configureImu(uint8_t addr) {
  if (!i2cWriteByte(addr, REG_CTRL3_C, 0x44)) return false;
  if (!i2cWriteByte(addr, REG_CTRL1_XL, 0x30)) return false;
  if (!i2cWriteByte(addr, REG_CTRL2_G, 0x30)) return false;
  delay(20);
  return true;
}

bool initImuIfNeeded() {
  if (imuReady) return true;
  uint32_t now = millis();
  if ((uint32_t)(now - lastImuInitAttemptMs) < IMU_REINIT_INTERVAL_MS) return false;
  lastImuInitAttemptMs = now;

  uint8_t candidates[2] = {0x6A, 0x6B};
  for (uint8_t i = 0; i < 2; ++i) {
    uint8_t addr = candidates[i];
    uint8_t who = 0;
    if (!i2cReadBytes(addr, REG_WHO_AM_I, &who, 1)) continue;
    if (who != WHO_AM_I_VALUE) continue;
    if (!configureImu(addr)) continue;

    imuAddress = addr;
    imuReady = true;
    calibrated = false;
    calibSumMag = 0.0f;
    calibCount = 0;
    confirmCount = 0;
    baselineMagG = 1.0f;
    Serial.printf("[IMU] ready at 0x%02X\n", imuAddress);
    return true;
  }

  Serial.println("[IMU] not detected; retrying");
  return false;
}

bool readImuSample(ImuSample &s) {
  if (!imuReady) return false;
  uint8_t raw[12] = {0};
  if (!i2cReadBytes(imuAddress, REG_OUTX_L_G, raw, sizeof(raw))) {
    imuReady = false;
    Serial.println("[IMU] read failed; marked offline");
    return false;
  }

  int16_t gxRaw = (int16_t)((raw[1] << 8) | raw[0]);
  int16_t gyRaw = (int16_t)((raw[3] << 8) | raw[2]);
  int16_t gzRaw = (int16_t)((raw[5] << 8) | raw[4]);
  int16_t axRaw = (int16_t)((raw[7] << 8) | raw[6]);
  int16_t ayRaw = (int16_t)((raw[9] << 8) | raw[8]);
  int16_t azRaw = (int16_t)((raw[11] << 8) | raw[10]);

  s.gx = gxRaw * 0.00875f;
  s.gy = gyRaw * 0.00875f;
  s.gz = gzRaw * 0.00875f;
  s.ax = axRaw * 0.000061f;
  s.ay = ayRaw * 0.000061f;
  s.az = azRaw * 0.000061f;
  return true;
}

float accelMagnitudeG(const ImuSample &s) {
  return sqrtf((s.ax * s.ax) + (s.ay * s.ay) + (s.az * s.az));
}

float gyroMaxDps(const ImuSample &s) {
  float a = fabsf(s.gx);
  float b = fabsf(s.gy);
  float c = fabsf(s.gz);
  return max(a, max(b, c));
}

void setup() {
  Serial.begin(115200);
  delay(250);
  Serial.println("\n[BOOT] Door-force MQTT node start");
  Serial.printf(
      "[FW] door_force_mqtt 2026-03-13 wifi_retry=%lu wifi_timeout=%lu\n",
      (unsigned long)WIFI_RETRY_INTERVAL_MS,
      (unsigned long)WIFI_CONNECT_TIMEOUT_MS);

  if (STATUS_LED_PIN >= 0) {
    pinMode(STATUS_LED_PIN, OUTPUT);
    setStatusLed(false);
  }

  snprintf(mqttClientId, sizeof(mqttClientId), "%s-client", NODE_ID);
  mqttTopicEvent(topicEvent, sizeof(topicEvent), MQTT_TOPIC_ROOT, NODE_ID);
  mqttTopicStatus(topicStatus, sizeof(topicStatus), MQTT_TOPIC_ROOT, NODE_ID);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, 400000);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(true);
  WiFi.setAutoReconnect(false);
  WiFi.persistent(false);
  beginWiFiConnection();
}

void loop() {
  ensureWiFi();
  ensureMqtt();
  mqttClient.loop();
  initImuIfNeeded();
  updateLedPattern();

  uint32_t now = millis();
  if (imuReady && (uint32_t)(now - lastSampleMs) >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;
    ImuSample sample;
    if (readImuSample(sample)) {
      float mag = accelMagnitudeG(sample);
      float gmax = gyroMaxDps(sample);

      if (!calibrated) {
        calibSumMag += mag;
        calibCount++;
        if (calibCount >= CALIBRATION_SAMPLES) {
          baselineMagG = calibSumMag / (float)calibCount;
          calibrated = true;
          Serial.printf("[IMU] calibration complete baseline=%.4f g\n", baselineMagG);
        }
      } else {
        float delta = fabsf(mag - baselineMagG);
        bool trigger = (delta >= ACCEL_DELTA_THRESHOLD_G) || (gmax >= GYRO_THRESHOLD_DPS);

        if (trigger) confirmCount++;
        else confirmCount = 0;

        if (delta <= BASELINE_UPDATE_MAX_DELTA_G && gmax <= BASELINE_UPDATE_MAX_GYRO_DPS) {
          baselineMagG = baselineMagG * (1.0f - BASELINE_ALPHA) + mag * BASELINE_ALPHA;
        }

        if (confirmCount >= FORCE_CONFIRM_SAMPLES && (uint32_t)(now - lastForceEventMs) >= MIN_FORCE_EVENT_GAP_MS) {
          float score = max(delta / max(ACCEL_DELTA_THRESHOLD_G, 0.01f), gmax / max(GYRO_THRESHOLD_DPS, 1.0f));
          String note = "d=" + String(delta, 3) + " g=" + String(gmax, 1) + " mag=" + String(mag, 3);
          emitEvent("DOOR_FORCE", score, "score", note, true);
          lastForceEventMs = now;
          confirmCount = 0;
        }
      }
    }
  }
  publishImuStateStatusIfChanged();

  processPendingEvent();
  delay(10);
}
