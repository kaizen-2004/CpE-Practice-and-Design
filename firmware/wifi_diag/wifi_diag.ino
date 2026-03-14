#include <WiFi.h>
#include "esp_wifi.h"

/*
  ESP32-C3 Wi-Fi Diagnostic Sketch
  Purpose: verify Wi-Fi connection stability only (no sensor logic).

  Edit these before upload.
*/
const char* WIFI_SSID = "condo2026";
const char* WIFI_PASSWORD = "condo2026";

// Optional MAC override test. Keep disabled unless needed.
static const bool FORCE_TEST_MAC = false;
static const uint8_t TEST_MAC[6] = {0x7C, 0xDF, 0xA1, 0x66, 0x77, 0x88};

static const uint32_t STATUS_PRINT_MS = 1000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
static const uint32_t WIFI_RETRY_INTERVAL_MS = 15000;

uint32_t lastStatusMs = 0;
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

const char* wlStatusText(wl_status_t s) {
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

const char* reasonText(uint8_t reason) {
  switch (reason) {
    case 2: return "AUTH_EXPIRE";
    case 3: return "AUTH_LEAVE";
    case 4: return "ASSOC_EXPIRE";
    case 6: return "NOT_AUTHED";
    case 7: return "NOT_ASSOCED";
    case 8: return "ASSOC_LEAVE";
    case 15: return "4WAY_HANDSHAKE_TIMEOUT";
    case 201: return "NO_AP_FOUND";
    case 202: return "AUTH_FAIL";
    case 205: return "CONNECTION_FAIL";
    default: return "OTHER";
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
      Serial.printf("[WiFi] GOT_IP: %s RSSI=%d\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      break;
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
      Serial.printf("[WiFi] Disconnected reason=%u (%s) status=%s\n",
                    info.wifi_sta_disconnected.reason,
                    reasonText(info.wifi_sta_disconnected.reason),
                    wlStatusText(WiFi.status()));
      break;
    default:
      break;
  }
}

void scanTarget() {
  Serial.printf("[WiFi] Scanning for SSID '%s'...\n", WIFI_SSID);
  int n = WiFi.scanNetworks(false, true);
  if (n < 0) {
    Serial.println("[WiFi] Scan failed");
    return;
  }
  Serial.printf("[WiFi] Scan found %d network(s)\n", n);

  bool found = false;
  for (int i = 0; i < n; ++i) {
    if (WiFi.SSID(i) == String(WIFI_SSID)) {
      found = true;
      Serial.printf("[WiFi] Target found: RSSI=%d ch=%d enc=%d\n",
                    WiFi.RSSI(i), WiFi.channel(i), (int)WiFi.encryptionType(i));
      break;
    }
  }
  if (!found) {
    Serial.println("[WiFi] Target SSID not found");
  }
  WiFi.scanDelete();
}

void beginWiFiConnection() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  Serial.printf("[WiFi] begin('%s')\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWiFiBeginAt = millis();
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
  Serial.printf("[WiFi] Reconnect attempt... (status=%s)\n", wlStatusText(status));
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

void setup() {
  Serial.begin(115200);
  delay(1200);
  Serial.println("\n[BOOT] WiFi-only diagnostic sketch");

  WiFi.onEvent(onWiFiEvent);
  WiFi.setSleep(false);

  Serial.printf("[WiFi] MAC before: %s\n", WiFi.macAddress().c_str());
  if (FORCE_TEST_MAC) {
    uint8_t mac[6];
    memcpy(mac, TEST_MAC, sizeof(mac));
    esp_err_t err = esp_wifi_set_mac(WIFI_IF_STA, mac);
    Serial.printf("[WiFi] set_mac err=%d\n", (int)err);
    Serial.printf("[WiFi] MAC after : %s\n", WiFi.macAddress().c_str());
  }

  delay(100);
  scanTarget();
  connectWiFiBlocking();
}

void loop() {
  uint32_t now = millis();
  maintainWiFiConnection();

  if (now - lastStatusMs >= STATUS_PRINT_MS) {
    lastStatusMs = now;
    wl_status_t s = WiFi.status();
    if (s == WL_CONNECTED) {
      Serial.printf("[STAT] %s ip=%s rssi=%d\n",
                    wlStatusText(s), WiFi.localIP().toString().c_str(), WiFi.RSSI());
    } else {
      Serial.printf("[STAT] %s\n", wlStatusText(s));
    }
  }

  delay(10);
}
