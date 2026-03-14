#include <WiFi.h>
#include <HTTPClient.h>

/*
  Smoke Node 2 (ESP32-C3 + MQ-2)
  Node ID: mq2_door
  Endpoint: POST /api/sensors/event

  Edit these values before upload.
*/
const char* WIFI_SSID = "condo2026";
const char* WIFI_PASSWORD = "condo2026";
const char* SERVER_URL = "http://192.168.1.50:5000/api/sensors/event";
const char* API_KEY = "";  // Optional. Leave empty to disable X-API-KEY header.

const char* NODE_ID = "mq2_door";
const char* ROOM_NAME = "Door Entrance Area";

// Hardware pins (ESP32-C3 Dev Module assumptions)
static const int MQ2_ADC_PIN = 0;       // MQ-2 AO -> GPIO0 (ADC)
static const int STATUS_LED_PIN = 8;    // Set to -1 if your board has no LED
static const bool STATUS_LED_ACTIVE_LOW = true;

// ADC + detection tuning
static const int ADC_SAMPLES = 8;
static const int ADC_HIGH_THRESHOLD = 2200;   // Trigger SMOKE_HIGH at/above this value
static const int ADC_CLEAR_THRESHOLD = 1900;  // Clear latched smoke state at/below this
static const uint8_t HIGH_CONFIRM_SAMPLES = 3;
static const uint8_t CLEAR_CONFIRM_SAMPLES = 5;

// Timing
static const uint32_t SAMPLE_INTERVAL_MS = 1000;
static const uint32_t HEARTBEAT_INTERVAL_MS = 60000;
static const uint32_t MIN_CRITICAL_EVENT_GAP_MS = 15000;
static const uint32_t WIFI_RETRY_INTERVAL_MS = 15000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
static const uint32_t HTTP_RETRY_INTERVAL_MS = 5000;
static const uint32_t HTTP_TIMEOUT_MS = 5000;

struct PendingEvent {
  bool active = false;
  String event;
  int value = 0;
  String note;
  uint32_t nextAttemptMs = 0;
};

PendingEvent pendingEvent;

bool smokeLatched = false;
uint8_t highCount = 0;
uint8_t clearCount = 0;

uint32_t lastSampleMs = 0;
uint32_t lastHeartbeatMs = 0;
uint32_t lastCriticalEventMs = 0;
uint32_t lastWiFiReconnectAttemptAt = 0;
uint32_t lastWiFiBeginAt = 0;

bool isConfiguredValue(const char* value) {
  if (value == nullptr || strlen(value) == 0) {
    return false;
  }
  return strncmp(value, "YOUR_", 5) != 0;
}

bool hasWiFiConfig() {
  return isConfiguredValue(WIFI_SSID) && isConfiguredValue(WIFI_PASSWORD);
}

const char* wifiStatusText(wl_status_t s) {
  switch (s) {
    case WL_IDLE_STATUS: return "IDLE";
    case WL_NO_SSID_AVAIL: return "NO_SSID";
    case WL_SCAN_COMPLETED: return "SCAN_DONE";
    case WL_CONNECTED: return "CONNECTED";
    case WL_CONNECT_FAILED: return "CONNECT_FAILED";
    case WL_CONNECTION_LOST: return "CONNECTION_LOST";
    case WL_DISCONNECTED: return "DISCONNECTED";
    default: return "UNKNOWN";
  }
}

void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  switch (event) {
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

void beginWiFiConnection() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWiFiBeginAt = millis();
}

void printScanForTarget() {
  Serial.printf("[WiFi] Scanning for SSID '%s'...\n", WIFI_SSID);
  int n = WiFi.scanNetworks(false, true);
  if (n < 0) {
    Serial.println("[WiFi] Scan failed");
    return;
  }
  Serial.printf("[WiFi] Scan found %d network(s)\n", n);
  bool found = false;
  for (int i = 0; i < n; ++i) {
    String ssid = WiFi.SSID(i);
    if (ssid == String(WIFI_SSID)) {
      found = true;
      Serial.printf(
        "[WiFi] Target found: ssid=%s rssi=%d ch=%d enc=%d\n",
        ssid.c_str(),
        WiFi.RSSI(i),
        WiFi.channel(i),
        (int)WiFi.encryptionType(i)
      );
      break;
    }
  }
  if (!found) {
    Serial.println("[WiFi] Target SSID not found in scan result");
  }
  WiFi.scanDelete();
}

String jsonEscape(const String& in) {
  String out;
  out.reserve(in.length() + 8);
  for (size_t i = 0; i < in.length(); ++i) {
    char c = in.charAt(i);
    if (c == '\\' || c == '"') {
      out += '\\';
      out += c;
    } else if (c == '\n') {
      out += "\\n";
    } else if (c == '\r') {
      out += "\\r";
    } else {
      out += c;
    }
  }
  return out;
}

void setStatusLed(bool on) {
  if (STATUS_LED_PIN < 0) {
    return;
  }
  int level = on ? HIGH : LOW;
  if (STATUS_LED_ACTIVE_LOW) {
    level = on ? LOW : HIGH;
  }
  digitalWrite(STATUS_LED_PIN, level);
}

void updateLedPattern() {
  if (WiFi.status() == WL_CONNECTED) {
    setStatusLed(true);
    return;
  }
  bool blinkOn = ((millis() / 300) % 2) == 0;
  setStatusLed(blinkOn);
}

void maintainWiFiConnection() {
  if (!hasWiFiConfig()) {
    return;
  }

  wl_status_t status = WiFi.status();
  if (status == WL_CONNECTED) {
    return;
  }

  uint32_t now = millis();
  // In-progress join is commonly reported as WL_IDLE_STATUS.
  if (status == WL_IDLE_STATUS) {
    if ((uint32_t)(now - lastWiFiBeginAt) < WIFI_CONNECT_TIMEOUT_MS) {
      return;
    }
  }

  if ((uint32_t)(now - lastWiFiReconnectAttemptAt) < WIFI_RETRY_INTERVAL_MS) {
    return;
  }

  lastWiFiReconnectAttemptAt = now;
  Serial.printf("[WiFi] Reconnect attempt to %s ... (status=%s)\n", WIFI_SSID, wifiStatusText(status));
  WiFi.disconnect();
  delay(20);
  beginWiFiConnection();
}

void connectWiFiBlocking() {
  if (!hasWiFiConfig()) {
    Serial.println("[WiFi] Credentials not configured.");
    return;
  }

  beginWiFiConnection();

  Serial.printf("[WiFi] Connecting to SSID: %s\n", WIFI_SSID);
  uint32_t startedAt = millis();

  while (WiFi.status() != WL_CONNECTED &&
         (uint32_t)(millis() - startedAt) < WIFI_CONNECT_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] Connected. IP=%s RSSI=%d\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("[WiFi] Initial connect failed. Will retry in loop.");
  }
}

int readMq2Raw() {
  long sum = 0;
  for (int i = 0; i < ADC_SAMPLES; ++i) {
    sum += analogRead(MQ2_ADC_PIN);
    delay(2);
  }
  return static_cast<int>(sum / ADC_SAMPLES);
}

bool postEventNow(const String& eventName, int value, const String& note) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(SERVER_URL)) {
    Serial.println("[HTTP] begin() failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  if (API_KEY && API_KEY[0] != '\0') {
    http.addHeader("X-API-KEY", API_KEY);
  }

  String payload;
  payload.reserve(256);
  payload += "{\"node\":\"" + jsonEscape(String(NODE_ID)) + "\"";
  payload += ",\"event\":\"" + jsonEscape(eventName) + "\"";
  payload += ",\"room\":\"" + jsonEscape(String(ROOM_NAME)) + "\"";
  payload += ",\"value\":" + String(value);
  payload += ",\"unit\":\"adc_raw\"";
  payload += ",\"note\":\"" + jsonEscape(note) + "\"";
  payload += "}";

  int code = http.POST(payload);
  String body = http.getString();
  http.end();

  bool ok = (code >= 200 && code < 300);
  if (ok) {
    Serial.printf("[HTTP] %s sent (code=%d)\n", eventName.c_str(), code);
  } else {
    Serial.printf("[HTTP] send failed for %s (code=%d, body=%s)\n",
                  eventName.c_str(), code, body.c_str());
  }
  return ok;
}

void queuePending(const String& eventName, int value, const String& note) {
  pendingEvent.active = true;
  pendingEvent.event = eventName;
  pendingEvent.value = value;
  pendingEvent.note = note;
  pendingEvent.nextAttemptMs = 0;
}

void emitEvent(const String& eventName, int value, const String& note, bool highPriority) {
  if (pendingEvent.active && !highPriority) {
    // Keep older pending event until it is delivered.
    return;
  }

  if (pendingEvent.active && highPriority) {
    // Replace non-critical pending data with critical event.
    pendingEvent.active = false;
  }

  if (!postEventNow(eventName, value, note)) {
    queuePending(eventName, value, note);
  }
}

void processPendingEvent() {
  if (!pendingEvent.active) {
    return;
  }

  uint32_t now = millis();
  if (now < pendingEvent.nextAttemptMs) {
    return;
  }

  if (postEventNow(pendingEvent.event, pendingEvent.value, pendingEvent.note)) {
    pendingEvent.active = false;
    return;
  }

  pendingEvent.nextAttemptMs = now + HTTP_RETRY_INTERVAL_MS;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  if (STATUS_LED_PIN >= 0) {
    pinMode(STATUS_LED_PIN, OUTPUT);
    setStatusLed(false);
  }

  analogReadResolution(12);
  analogSetPinAttenuation(MQ2_ADC_PIN, ADC_11db);

  WiFi.onEvent(onWiFiEvent);
  WiFi.setSleep(false);
  delay(50);
  printScanForTarget();
  connectWiFiBlocking();

  Serial.println("\n[BOOT] Smoke Node 2 started");
  Serial.printf("[BOOT] node=%s room=%s pin=%d\n", NODE_ID, ROOM_NAME, MQ2_ADC_PIN);
}

void loop() {
  maintainWiFiConnection();
  updateLedPattern();

  uint32_t now = millis();

  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;

    int raw = readMq2Raw();
    Serial.printf("[SAMPLE] adc=%d latched=%d wifi=%d\n", raw, smokeLatched ? 1 : 0,
                  WiFi.status() == WL_CONNECTED ? 1 : 0);

    if (raw >= ADC_HIGH_THRESHOLD) {
      highCount++;
      clearCount = 0;
    } else if (raw <= ADC_CLEAR_THRESHOLD) {
      clearCount++;
      highCount = 0;
    } else {
      // In hysteresis band.
      highCount = 0;
      clearCount = 0;
    }

    if (!smokeLatched && highCount >= HIGH_CONFIRM_SAMPLES) {
      smokeLatched = true;
      highCount = 0;

      if (now - lastCriticalEventMs >= MIN_CRITICAL_EVENT_GAP_MS) {
        String note = "threshold_crossed";
        emitEvent("SMOKE_HIGH", raw, note, true);
        lastCriticalEventMs = now;
      }
    }

    if (smokeLatched && clearCount >= CLEAR_CONFIRM_SAMPLES) {
      smokeLatched = false;
      clearCount = 0;
      emitEvent("SMOKE_NORMAL", raw, "returned_below_clear_threshold", false);
    }

    if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
      lastHeartbeatMs = now;
      String note = "heartbeat rssi=" + String(WiFi.RSSI()) + " latched=" + String(smokeLatched ? 1 : 0);
      emitEvent("SMOKE_HEARTBEAT", raw, note, false);
    }
  }

  processPendingEvent();
  delay(15);
}
