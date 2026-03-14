#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>
#include <math.h>

#include "espnow_packet.h"

/*
  Door-Force Node (ESP32-C3 + GY-LSM6DS3) via ESP-NOW
  Node ID: door_force

  Transport:
  - Sends events to an ESP-NOW gateway (broadcast by default)
  - Gateway forwards to Raspberry Pi over USB serial
*/

const char *NODE_ID = "door_force";
const char *ROOM_NAME = "Door Entrance Area";

// ESP-NOW transport configuration
static const uint8_t ESPNOW_CHANNEL = 6;
static const bool ESPNOW_USE_BROADCAST = true;
static const uint8_t ESPNOW_GATEWAY_MAC[6] = {0xE0, 0x72, 0xA1, 0x68, 0xC1, 0x34}; // Current gateway MAC; update if gateway hardware changes
static const uint8_t ESPNOW_BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static const uint32_t ESPNOW_SEND_WAIT_MS = 80;
static const uint32_t ESPNOW_RETRY_INTERVAL_MS = 5000;

// ESP32-C3 I2C pin assumptions (edit if needed)
static const int I2C_SDA_PIN = 8;
static const int I2C_SCL_PIN = 9;

// Optional status LED
static const int STATUS_LED_PIN = -1; // Set to a valid pin if you want a status LED
static const bool STATUS_LED_ACTIVE_LOW = true;

// Timing
static const uint32_t SAMPLE_INTERVAL_MS = 50;
static const uint32_t HEARTBEAT_INTERVAL_MS = 15000;
static const uint32_t MIN_FORCE_EVENT_GAP_MS = 10000;
static const uint32_t EVENT_RETRY_INTERVAL_MS = 5000;
static const uint32_t IMU_REINIT_INTERVAL_MS = 5000;

// Detection tuning
static const uint16_t CALIBRATION_SAMPLES = 100;
static const uint8_t FORCE_CONFIRM_SAMPLES = 2;
static const float ACCEL_DELTA_THRESHOLD_G = 0.35f;
static const float GYRO_THRESHOLD_DPS = 90.0f;
static const float BASELINE_ALPHA = 0.01f;
static const float BASELINE_UPDATE_MAX_DELTA_G = 0.12f;
static const float BASELINE_UPDATE_MAX_GYRO_DPS = 25.0f;

// LSM6DS3 register map
static const uint8_t REG_WHO_AM_I = 0x0F;
static const uint8_t REG_CTRL1_XL = 0x10;
static const uint8_t REG_CTRL2_G = 0x11;
static const uint8_t REG_CTRL3_C = 0x12;
static const uint8_t REG_OUTX_L_G = 0x22;
static const uint8_t REG_OUTX_L_XL = 0x28;
static const uint8_t WHO_AM_I_VALUE = 0x69;

struct ImuSample
{
  float ax = 0.0f;
  float ay = 0.0f;
  float az = 0.0f;
  float gx = 0.0f;
  float gy = 0.0f;
  float gz = 0.0f;
};

struct PendingEvent
{
  bool active = false;
  String event;
  float value = 0.0f;
  String unit;
  String note;
  uint32_t nextAttemptMs = 0;
};

PendingEvent pendingEvent;

bool imuReady = false;
bool calibrated = false;
uint8_t imuAddress = 0;

float baselineMagG = 1.0f;
float calibSumMag = 0.0f;
uint16_t calibCount = 0;
uint8_t confirmCount = 0;

uint32_t lastSampleMs = 0;
uint32_t lastHeartbeatMs = 0;
uint32_t lastForceEventMs = 0;
uint32_t lastImuInitAttemptMs = 0;
uint32_t lastEspNowInitAttemptMs = 0;
uint32_t eventSeq = 0;

bool espNowReady = false;
volatile bool sendCallbackDone = false;
volatile esp_now_send_status_t sendCallbackStatus = ESP_NOW_SEND_FAIL;

void setStatusLed(bool on)
{
  if (STATUS_LED_PIN < 0)
  {
    return;
  }
  int level = on ? HIGH : LOW;
  if (STATUS_LED_ACTIVE_LOW)
  {
    level = on ? LOW : HIGH;
  }
  digitalWrite(STATUS_LED_PIN, level);
}

void updateLedPattern()
{
  if (!imuReady)
  {
    bool blinkOn = ((millis() / 120) % 2) == 0;
    setStatusLed(blinkOn);
    return;
  }

  if (espNowReady)
  {
    setStatusLed(true);
    return;
  }

  bool blinkOn = ((millis() / 300) % 2) == 0;
  setStatusLed(blinkOn);
}

void peerAddress(uint8_t out[6])
{
  if (ESPNOW_USE_BROADCAST)
  {
    memcpy(out, ESPNOW_BROADCAST_MAC, 6);
  }
  else
  {
    memcpy(out, ESPNOW_GATEWAY_MAC, 6);
  }
}

void onEspNowSent(const esp_now_send_info_t *txInfo, esp_now_send_status_t status)
{
  (void)txInfo;
  sendCallbackStatus = status;
  sendCallbackDone = true;
}

bool initEspNow()
{
  if (espNowReady)
  {
    return true;
  }

  uint32_t now = millis();
  if ((uint32_t)(now - lastEspNowInitAttemptMs) < ESPNOW_RETRY_INTERVAL_MS)
  {
    return false;
  }
  lastEspNowInitAttemptMs = now;

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.disconnect();
  uint32_t wifiStartAt = millis();
  while (!WiFi.STA.started() && (uint32_t)(millis() - wifiStartAt) < 2000)
  {
    delay(10);
  }

  int chResult = WiFi.setChannel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (chResult != ESP_OK)
  {
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_wifi_set_promiscuous(false);
  }

  esp_now_deinit();
  if (esp_now_init() != ESP_OK)
  {
    Serial.println("[ESPNOW] init failed");
    return false;
  }

  if (esp_now_register_send_cb(onEspNowSent) != ESP_OK)
  {
    Serial.println("[ESPNOW] send callback register failed");
    esp_now_deinit();
    return false;
  }

  esp_now_peer_info_t peerInfo = {};
  peerAddress(peerInfo.peer_addr);
  peerInfo.channel = 0; // Use current interface channel; avoids stale fixed-channel peer state
  peerInfo.ifidx = WIFI_IF_STA;
  peerInfo.encrypt = false;

  esp_err_t peerErr = esp_now_add_peer(&peerInfo);
  if (peerErr != ESP_OK && peerErr != ESP_ERR_ESPNOW_EXIST)
  {
    Serial.printf("[ESPNOW] add peer failed err=%d\n", (int)peerErr);
    esp_now_deinit();
    return false;
  }

  espNowReady = true;
  uint8_t destAddr[6];
  peerAddress(destAddr);
  Serial.printf("[ESPNOW] ready cfg_ch=%u actual_ch=%u mode=%s local_mac=%s peer=%02X:%02X:%02X:%02X:%02X:%02X\n",
                ESPNOW_CHANNEL,
                WiFi.channel(),
                ESPNOW_USE_BROADCAST ? "broadcast" : "unicast",
                WiFi.macAddress().c_str(),
                destAddr[0], destAddr[1], destAddr[2], destAddr[3], destAddr[4], destAddr[5]);
  return true;
}

void maintainEspNow()
{
  if (!espNowReady)
  {
    initEspNow();
  }
}

bool sendPacketNow(EspNowSensorPacket &pkt)
{
  if (!espNowReady)
  {
    return false;
  }

  uint8_t destAddr[6];
  peerAddress(destAddr);

  sendCallbackDone = false;
  sendCallbackStatus = ESP_NOW_SEND_FAIL;

  esp_err_t err = esp_now_send(destAddr, reinterpret_cast<const uint8_t *>(&pkt), sizeof(pkt));
  if (err != ESP_OK)
  {
    Serial.printf("[ESPNOW] send enqueue failed err=%d\n", (int)err);
    if (err == ESP_ERR_ESPNOW_NOT_INIT || err == ESP_ERR_ESPNOW_INTERNAL)
    {
      espNowReady = false;
    }
    return false;
  }

  uint32_t startedAt = millis();
  while (!sendCallbackDone && (uint32_t)(millis() - startedAt) < ESPNOW_SEND_WAIT_MS)
  {
    delay(1);
  }

  if (!sendCallbackDone)
  {
    Serial.println("[ESPNOW] send timeout");
    return false;
  }

  bool ok = (sendCallbackStatus == ESP_NOW_SEND_SUCCESS);
  if (!ok)
  {
    Serial.printf("[ESPNOW] send status=%d\n", (int)sendCallbackStatus);
  }
  return ok;
}

bool sendEventNow(const String &eventName, float value, const String &unit, const String &note)
{
  EspNowSensorPacket pkt;
  initEspNowPacket(pkt);

  pkt.seq = ++eventSeq;
  pkt.uptimeMs = millis();
  pkt.value = value;

  espnowSafeCopy(pkt.node, sizeof(pkt.node), NODE_ID);
  espnowSafeCopy(pkt.room, sizeof(pkt.room), ROOM_NAME);
  espnowSafeCopy(pkt.event, sizeof(pkt.event), eventName.c_str());
  espnowSafeCopy(pkt.unit, sizeof(pkt.unit), unit.c_str());
  espnowSafeCopy(pkt.note, sizeof(pkt.note), note.c_str());

  bool ok = sendPacketNow(pkt);
  if (ok)
  {
    Serial.printf("[ESPNOW] %s sent seq=%lu\n", eventName.c_str(), (unsigned long)pkt.seq);
  }
  return ok;
}

void queuePending(const String &eventName, float value, const String &unit, const String &note)
{
  pendingEvent.active = true;
  pendingEvent.event = eventName;
  pendingEvent.value = value;
  pendingEvent.unit = unit;
  pendingEvent.note = note;
  pendingEvent.nextAttemptMs = 0;
}

void emitEvent(const String &eventName, float value, const String &unit, const String &note, bool highPriority)
{
  if (pendingEvent.active && !highPriority)
  {
    return;
  }

  if (pendingEvent.active && highPriority)
  {
    pendingEvent.active = false;
  }

  if (!sendEventNow(eventName, value, unit, note))
  {
    queuePending(eventName, value, unit, note);
  }
}

void processPendingEvent()
{
  if (!pendingEvent.active)
  {
    return;
  }

  uint32_t now = millis();
  if (now < pendingEvent.nextAttemptMs)
  {
    return;
  }

  if (sendEventNow(pendingEvent.event, pendingEvent.value, pendingEvent.unit, pendingEvent.note))
  {
    pendingEvent.active = false;
    return;
  }

  pendingEvent.nextAttemptMs = now + EVENT_RETRY_INTERVAL_MS;
}

bool i2cReadBytes(uint8_t addr, uint8_t reg, uint8_t *out, size_t len)
{
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0)
  {
    return false;
  }

  size_t got = Wire.requestFrom((int)addr, (int)len);
  if (got != len)
  {
    return false;
  }

  for (size_t i = 0; i < len; ++i)
  {
    out[i] = Wire.read();
  }
  return true;
}

bool i2cWriteByte(uint8_t addr, uint8_t reg, uint8_t val)
{
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool configureImu(uint8_t addr)
{
  if (!i2cWriteByte(addr, REG_CTRL3_C, 0x44))
  {
    return false;
  }

  if (!i2cWriteByte(addr, REG_CTRL1_XL, 0x30))
  {
    return false;
  }

  if (!i2cWriteByte(addr, REG_CTRL2_G, 0x30))
  {
    return false;
  }

  delay(20);
  return true;
}

bool initImuIfNeeded()
{
  if (imuReady)
  {
    return true;
  }

  uint32_t now = millis();
  if (now - lastImuInitAttemptMs < IMU_REINIT_INTERVAL_MS)
  {
    return false;
  }
  lastImuInitAttemptMs = now;

  uint8_t candidates[2] = {0x6A, 0x6B};
  for (uint8_t i = 0; i < 2; ++i)
  {
    uint8_t addr = candidates[i];
    uint8_t who = 0;
    if (!i2cReadBytes(addr, REG_WHO_AM_I, &who, 1))
    {
      continue;
    }
    if (who != WHO_AM_I_VALUE)
    {
      continue;
    }
    if (!configureImu(addr))
    {
      continue;
    }

    imuAddress = addr;
    imuReady = true;
    calibrated = false;
    calibSumMag = 0.0f;
    calibCount = 0;
    confirmCount = 0;
    baselineMagG = 1.0f;

    Serial.printf("[IMU] LSM6DS3 ready at 0x%02X\n", imuAddress);
    return true;
  }

  Serial.println("[IMU] LSM6DS3 not detected. Re-trying...");
  return false;
}

bool readImuSample(ImuSample &s)
{
  if (!imuReady)
  {
    return false;
  }

  uint8_t raw[12] = {0};
  if (!i2cReadBytes(imuAddress, REG_OUTX_L_G, raw, sizeof(raw)))
  {
    imuReady = false;
    Serial.println("[IMU] Read failed; IMU marked offline");
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

float accelMagnitudeG(const ImuSample &s)
{
  return sqrtf((s.ax * s.ax) + (s.ay * s.ay) + (s.az * s.az));
}

float gyroMaxDps(const ImuSample &s)
{
  float a = fabsf(s.gx);
  float b = fabsf(s.gy);
  float c = fabsf(s.gz);
  return max(a, max(b, c));
}

void setup()
{
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[BOOT] Door-force ESP-NOW node start");

  if (STATUS_LED_PIN >= 0)
  {
    pinMode(STATUS_LED_PIN, OUTPUT);
    setStatusLed(false);
  }

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, 400000);

  initEspNow();

  Serial.printf("[BOOT] node=%s room=%s sda=%d scl=%d\n", NODE_ID, ROOM_NAME, I2C_SDA_PIN, I2C_SCL_PIN);
}

void loop()
{
  maintainEspNow();
  initImuIfNeeded();
  updateLedPattern();

  uint32_t now = millis();

  if (imuReady && now - lastSampleMs >= SAMPLE_INTERVAL_MS)
  {
    lastSampleMs = now;

    ImuSample sample;
    if (readImuSample(sample))
    {
      float mag = accelMagnitudeG(sample);
      float gmax = gyroMaxDps(sample);

      if (!calibrated)
      {
        calibSumMag += mag;
        calibCount++;
        if (calibCount >= CALIBRATION_SAMPLES)
        {
          baselineMagG = calibSumMag / (float)calibCount;
          calibrated = true;
          Serial.printf("[IMU] Calibration complete. baseline=%.4f g\n", baselineMagG);
        }
      }
      else
      {
        float delta = fabsf(mag - baselineMagG);
        bool trigger = (delta >= ACCEL_DELTA_THRESHOLD_G) || (gmax >= GYRO_THRESHOLD_DPS);

        if (trigger)
        {
          confirmCount++;
        }
        else
        {
          confirmCount = 0;
        }

        if (delta <= BASELINE_UPDATE_MAX_DELTA_G && gmax <= BASELINE_UPDATE_MAX_GYRO_DPS)
        {
          baselineMagG = baselineMagG * (1.0f - BASELINE_ALPHA) + mag * BASELINE_ALPHA;
        }

        if (confirmCount >= FORCE_CONFIRM_SAMPLES && (now - lastForceEventMs >= MIN_FORCE_EVENT_GAP_MS))
        {
          float score = max(delta / max(ACCEL_DELTA_THRESHOLD_G, 0.01f), gmax / max(GYRO_THRESHOLD_DPS, 1.0f));
          String note = "delta_g=" + String(delta, 3) +
                        " gyro_max_dps=" + String(gmax, 1) +
                        " mag_g=" + String(mag, 3);
          emitEvent("DOOR_FORCE", score, "score", note, true);
          lastForceEventMs = now;
          confirmCount = 0;
          Serial.printf("[FORCE] Triggered score=%.3f delta=%.3f gyro=%.1f\n", score, delta, gmax);
        }

        Serial.printf("[SAMPLE] mag=%.3f delta=%.3f gyro=%.1f base=%.3f espnow=%d\n",
                      mag, delta, gmax, baselineMagG, espNowReady ? 1 : 0);
      }
    }
  }

  if (lastHeartbeatMs == 0 || now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS)
  {
    String note = "link=espnow imu=" + String(imuReady ? "ok" : "offline") +
                  " calibrated=" + String(calibrated ? "yes" : "no") +
                  " baseline_g=" + String(baselineMagG, 3);
    emitEvent("DOOR_HEARTBEAT", baselineMagG, "accel_mag_g", note, false);
    lastHeartbeatMs = now;
  }

  processPendingEvent();
  delay(10);
}
