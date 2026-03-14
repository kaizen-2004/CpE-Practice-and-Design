#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <math.h>

/*
  Door-Force Node (ESP32-C3 + GY-LSM6DS3)
  Node ID: door_force
  Endpoint: POST /api/sensors/event

  Edit these values before upload.
*/
const char *WIFI_SSID = "ThesisIoT";
const char *WIFI_PASSWORD = "condo2026";
const char *SERVER_URL = "http://192.168.50.1:5000/api/sensors/event";
const char *API_KEY = ""; // Optional. Leave empty to disable X-API-KEY header.

const char *NODE_ID = "door_force";
const char *ROOM_NAME = "Door Entrance Area";

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
static const uint32_t WIFI_RETRY_INTERVAL_MS = 15000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
static const uint32_t HTTP_RETRY_INTERVAL_MS = 5000;
static const uint32_t HTTP_TIMEOUT_MS = 5000;
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
uint32_t lastWiFiReconnectAttemptAt = 0;
uint32_t lastImuInitAttemptMs = 0;
uint32_t lastWiFiBeginAt = 0;

bool isConfiguredValue(const char *value)
{
  if (value == nullptr || strlen(value) == 0)
  {
    return false;
  }
  return strncmp(value, "YOUR_", 5) != 0;
}

bool hasWiFiConfig()
{
  return isConfiguredValue(WIFI_SSID) && isConfiguredValue(WIFI_PASSWORD);
}

const char *wifiStatusText(wl_status_t s)
{
  switch (s)
  {
  case WL_IDLE_STATUS:
    return "IDLE";
  case WL_NO_SSID_AVAIL:
    return "NO_SSID";
  case WL_SCAN_COMPLETED:
    return "SCAN_DONE";
  case WL_CONNECTED:
    return "CONNECTED";
  case WL_CONNECT_FAILED:
    return "CONNECT_FAILED";
  case WL_CONNECTION_LOST:
    return "CONNECTION_LOST";
  case WL_DISCONNECTED:
    return "DISCONNECTED";
  default:
    return "UNKNOWN";
  }
}

void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info)
{
  switch (event)
  {
  case ARDUINO_EVENT_WIFI_STA_START:
    Serial.println("[WiFi] STA started");
    break;
  case ARDUINO_EVENT_WIFI_STA_CONNECTED:
    Serial.println("[WiFi] Associated with AP");
    break;
  case ARDUINO_EVENT_WIFI_STA_GOT_IP:
    Serial.printf("[WiFi] Connected. IP=%s RSSI=%d\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    break;
  case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
    Serial.printf("[WiFi] Disconnected. reason=%d status=%s\n",
                  info.wifi_sta_disconnected.reason, wifiStatusText(WiFi.status()));
    break;
  default:
    break;
  }
}

void beginWiFiConnection()
{
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWiFiBeginAt = millis();
}

void printScanForTarget()
{
  Serial.printf("[WiFi] Scanning for SSID '%s'...\n", WIFI_SSID);
  int n = WiFi.scanNetworks(false, true);
  if (n < 0)
  {
    Serial.println("[WiFi] Scan failed");
    return;
  }
  Serial.printf("[WiFi] Scan found %d network(s)\n", n);
  bool found = false;
  for (int i = 0; i < n; ++i)
  {
    String ssid = WiFi.SSID(i);
    if (ssid == String(WIFI_SSID))
    {
      found = true;
      Serial.printf(
          "[WiFi] Target found: ssid=%s rssi=%d ch=%d enc=%d\n",
          ssid.c_str(),
          WiFi.RSSI(i),
          WiFi.channel(i),
          (int)WiFi.encryptionType(i));
      break;
    }
  }
  if (!found)
  {
    Serial.println("[WiFi] Target SSID not found in scan result");
  }
  WiFi.scanDelete();
}

String jsonEscape(const String &in)
{
  String out;
  out.reserve(in.length() + 8);
  for (size_t i = 0; i < in.length(); ++i)
  {
    char c = in.charAt(i);
    if (c == '\\' || c == '"')
    {
      out += '\\';
      out += c;
    }
    else if (c == '\n')
    {
      out += "\\n";
    }
    else if (c == '\r')
    {
      out += "\\r";
    }
    else
    {
      out += c;
    }
  }
  return out;
}

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

  if (WiFi.status() == WL_CONNECTED)
  {
    setStatusLed(true);
    return;
  }

  bool blinkOn = ((millis() / 300) % 2) == 0;
  setStatusLed(blinkOn);
}

void maintainWiFiConnection()
{
  if (!hasWiFiConfig())
  {
    return;
  }

  wl_status_t status = WiFi.status();
  if (status == WL_CONNECTED)
  {
    return;
  }

  uint32_t now = millis();
  // In-progress join is commonly reported as WL_IDLE_STATUS.
  if (status == WL_IDLE_STATUS)
  {
    if ((uint32_t)(now - lastWiFiBeginAt) < WIFI_CONNECT_TIMEOUT_MS)
    {
      return;
    }
  }

  if ((uint32_t)(now - lastWiFiReconnectAttemptAt) < WIFI_RETRY_INTERVAL_MS)
  {
    return;
  }

  lastWiFiReconnectAttemptAt = now;
  Serial.printf("[WiFi] Reconnect attempt to %s ... (status=%s)\n", WIFI_SSID, wifiStatusText(status));
  WiFi.disconnect();
  delay(20);
  beginWiFiConnection();
}

void connectWiFiBlocking()
{
  if (!hasWiFiConfig())
  {
    Serial.println("[WiFi] Credentials not configured.");
    return;
  }

  beginWiFiConnection();

  Serial.printf("[WiFi] Connecting to SSID: %s\n", WIFI_SSID);
  uint32_t startedAt = millis();

  while (WiFi.status() != WL_CONNECTED &&
         (uint32_t)(millis() - startedAt) < WIFI_CONNECT_TIMEOUT_MS)
  {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.printf("[WiFi] Connected. IP=%s RSSI=%d\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  }
  else
  {
    Serial.println("[WiFi] Initial connect failed. Will retry in loop.");
  }
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
  // BDU=1, IF_INC=1
  if (!i2cWriteByte(addr, REG_CTRL3_C, 0x44))
  {
    return false;
  }

  // Accelerometer: ODR=52 Hz, FS=+-2g
  if (!i2cWriteByte(addr, REG_CTRL1_XL, 0x30))
  {
    return false;
  }

  // Gyroscope: ODR=52 Hz, FS=245 dps
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

  // Sensitivity constants for selected full-scale settings
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

bool postEventNow(const String &eventName, float value, const String &unit, const String &note)
{
  if (WiFi.status() != WL_CONNECTED)
  {
    return false;
  }

  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(SERVER_URL))
  {
    Serial.println("[HTTP] begin() failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  if (API_KEY && API_KEY[0] != '\0')
  {
    http.addHeader("X-API-KEY", API_KEY);
  }

  String payload;
  payload.reserve(320);
  payload += "{\"node\":\"" + jsonEscape(String(NODE_ID)) + "\"";
  payload += ",\"event\":\"" + jsonEscape(eventName) + "\"";
  payload += ",\"room\":\"" + jsonEscape(String(ROOM_NAME)) + "\"";
  payload += ",\"value\":" + String(value, 3);
  payload += ",\"unit\":\"" + jsonEscape(unit) + "\"";
  payload += ",\"note\":\"" + jsonEscape(note) + "\"";
  payload += "}";

  int code = http.POST(payload);
  String body = http.getString();
  http.end();

  bool ok = (code >= 200 && code < 300);
  if (ok)
  {
    Serial.printf("[HTTP] %s sent (code=%d)\n", eventName.c_str(), code);
  }
  else
  {
    Serial.printf("[HTTP] send failed for %s (code=%d, body=%s)\n",
                  eventName.c_str(), code, body.c_str());
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

  if (!postEventNow(eventName, value, unit, note))
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

  if (postEventNow(pendingEvent.event, pendingEvent.value, pendingEvent.unit, pendingEvent.note))
  {
    pendingEvent.active = false;
    return;
  }

  pendingEvent.nextAttemptMs = now + HTTP_RETRY_INTERVAL_MS;
}

void setup()
{
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[BOOT] Door-force setup init");

  if (STATUS_LED_PIN >= 0)
  {
    pinMode(STATUS_LED_PIN, OUTPUT);
    setStatusLed(false);
  }

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, 400000);

  WiFi.onEvent(onWiFiEvent);
  WiFi.setSleep(false);
  delay(50);
  printScanForTarget();
  connectWiFiBlocking();

  Serial.println("\n[BOOT] Door-force node started");
  Serial.printf("[BOOT] node=%s room=%s sda=%d scl=%d\n", NODE_ID, ROOM_NAME, I2C_SDA_PIN, I2C_SCL_PIN);
}

void loop()
{
  maintainWiFiConnection();
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

        Serial.printf("[SAMPLE] mag=%.3f delta=%.3f gyro=%.1f base=%.3f wifi=%d\n",
                      mag, delta, gmax, baselineMagG,
                      WiFi.status() == WL_CONNECTED ? 1 : 0);
      }
    }
  }

  if (WiFi.status() == WL_CONNECTED &&
      (lastHeartbeatMs == 0 || now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS))
  {
    String note = "rssi=" + String(WiFi.RSSI()) +
                  " imu=" + String(imuReady ? "ok" : "offline") +
                  " calibrated=" + String(calibrated ? "yes" : "no") +
                  " baseline_g=" + String(baselineMagG, 3);
    emitEvent("DOOR_HEARTBEAT", baselineMagG, "accel_mag_g", note, false);
    lastHeartbeatMs = now;
  }

  processPendingEvent();
  delay(10);
}
