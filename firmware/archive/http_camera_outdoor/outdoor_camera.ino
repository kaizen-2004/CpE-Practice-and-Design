#include "esp_camera.h"
#include "img_converters.h"
#include "esp_http_server.h"

#include <WiFi.h>
#include <HTTPClient.h>

/*
  Outdoor Camera Node (ESP32-CAM AI Thinker)
  - MJPEG stream:   http://<device-ip>:81/stream
  - Snapshot still: http://<device-ip>/capture
  - Snapshot alias: http://<device-ip>/snapshot.jpg

  Optional backend heartbeat POST (cam_outdoor) to /api/sensors/event.
*/

// ---------------------------
// User-editable configuration
// ---------------------------
const char* WIFI_SSID = "condo2026";
const char* WIFI_PASSWORD = "condo2026";
const char* WIFI_HOSTNAME = "cam-outdoor";

const char* NODE_ID = "cam_outdoor";
const char* ROOM_NAME = "Door Entrance Area";

// Optional: leave empty to disable backend heartbeat POSTs.
const char* BACKEND_EVENT_URL = "";  // e.g. "http://192.168.1.50:5000/api/sensors/event"
const char* API_KEY = "";            // Optional X-API-KEY header

// Camera tuning
static const framesize_t CAMERA_FRAME_SIZE = FRAMESIZE_VGA; // QVGA/VGA/SVGA
static const int CAMERA_JPEG_QUALITY = 12;                  // lower=better quality, larger payload
static const uint32_t STREAM_FRAME_DELAY_MS = 70;           // approx FPS limiter (70ms ~14 FPS)

// Retry and heartbeat timing
static const uint32_t WIFI_RETRY_INTERVAL_MS = 15000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
static const uint32_t HTTP_RETRY_INTERVAL_MS = 5000;
static const uint32_t HTTP_TIMEOUT_MS = 5000;
static const uint32_t HEARTBEAT_INTERVAL_MS = 60000;

// ---------------------------
// AI Thinker ESP32-CAM pins
// ---------------------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define FLASH_LED_PIN      4

static const char* STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
static const char* STREAM_BOUNDARY = "\r\n--frame\r\n";
static const char* STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t cameraHttpd = nullptr;
httpd_handle_t streamHttpd = nullptr;
bool cameraServerRunning = false;

struct PendingEvent {
  bool active = false;
  String event;
  float value = 0.0f;
  String unit;
  String note;
  uint32_t nextAttemptMs = 0;
};

PendingEvent pendingEvent;

uint32_t lastWiFiReconnectAttemptAt = 0;
uint32_t lastWiFiBeginAt = 0;
uint32_t lastHeartbeatMs = 0;

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

bool backendEnabled() {
  return BACKEND_EVENT_URL && BACKEND_EVENT_URL[0] != '\0';
}

void beginWiFiConnection() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.setHostname(WIFI_HOSTNAME);
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

bool postEventNow(const String& eventName, float value, const String& unit, const String& note) {
  if (!backendEnabled()) {
    return true;
  }
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(BACKEND_EVENT_URL)) {
    Serial.println("[HTTP] begin() failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  if (API_KEY && API_KEY[0] != '\0') {
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
  if (ok) {
    Serial.printf("[HTTP] %s sent (code=%d)\n", eventName.c_str(), code);
  } else {
    Serial.printf("[HTTP] send failed for %s (code=%d, body=%s)\n",
                  eventName.c_str(), code, body.c_str());
  }
  return ok;
}

void queuePending(const String& eventName, float value, const String& unit, const String& note) {
  pendingEvent.active = true;
  pendingEvent.event = eventName;
  pendingEvent.value = value;
  pendingEvent.unit = unit;
  pendingEvent.note = note;
  pendingEvent.nextAttemptMs = 0;
}

void emitEvent(const String& eventName, float value, const String& unit, const String& note) {
  if (!backendEnabled()) {
    return;
  }

  if (!postEventNow(eventName, value, unit, note)) {
    queuePending(eventName, value, unit, note);
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

  if (postEventNow(pendingEvent.event, pendingEvent.value, pendingEvent.unit, pendingEvent.note)) {
    pendingEvent.active = false;
    return;
  }

  pendingEvent.nextAttemptMs = now + HTTP_RETRY_INTERVAL_MS;
}

esp_err_t indexHandler(httpd_req_t* req) {
  static const char PROGMEM INDEX_HTML[] =
      "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'/>"
      "<title>Outdoor Camera</title></head><body style='font-family:sans-serif'>"
      "<h3>Outdoor ESP32-CAM</h3>"
      "<p><a href='/capture'>Capture Snapshot</a> | <a href='/snapshot.jpg'>snapshot.jpg</a></p>"
      "<img src='http://";

  String ip = WiFi.localIP().toString();
  String page = String(INDEX_HTML) + ip + ":81/stream' style='max-width:100%;height:auto;border:1px solid #ccc'/>"
                  "</body></html>";

  httpd_resp_set_type(req, "text/html");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, page.c_str(), page.length());
}

esp_err_t captureHandler(httpd_req_t* req) {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  esp_err_t res = httpd_resp_send(req, reinterpret_cast<const char*>(fb->buf), fb->len);
  esp_camera_fb_return(fb);
  return res;
}

esp_err_t streamHandler(httpd_req_t* req) {
  esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) {
    return res;
  }
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  camera_fb_t* fb = nullptr;
  uint8_t* jpgBuf = nullptr;
  size_t jpgLen = 0;
  char partBuf[64];

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[CAM] Frame capture failed");
      res = ESP_FAIL;
    } else {
      if (fb->format != PIXFORMAT_JPEG) {
        bool ok = frame2jpg(fb, CAMERA_JPEG_QUALITY, &jpgBuf, &jpgLen);
        esp_camera_fb_return(fb);
        fb = nullptr;
        if (!ok) {
          Serial.println("[CAM] JPEG conversion failed");
          res = ESP_FAIL;
        }
      } else {
        jpgBuf = fb->buf;
        jpgLen = fb->len;
      }
    }

    if (res == ESP_OK) {
      size_t hlen = snprintf(partBuf, sizeof(partBuf), STREAM_PART, jpgLen);
      res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
      if (res == ESP_OK) {
        res = httpd_resp_send_chunk(req, partBuf, hlen);
      }
      if (res == ESP_OK) {
        res = httpd_resp_send_chunk(req, reinterpret_cast<const char*>(jpgBuf), jpgLen);
      }
    }

    if (fb) {
      esp_camera_fb_return(fb);
      fb = nullptr;
      jpgBuf = nullptr;
    } else if (jpgBuf) {
      free(jpgBuf);
      jpgBuf = nullptr;
    }

    if (res != ESP_OK) {
      break;
    }

    delay(STREAM_FRAME_DELAY_MS);
  }

  Serial.println("[HTTP] Stream client disconnected");
  return res;
}

void stopCameraServer() {
  if (streamHttpd) {
    httpd_stop(streamHttpd);
    streamHttpd = nullptr;
  }
  if (cameraHttpd) {
    httpd_stop(cameraHttpd);
    cameraHttpd = nullptr;
  }
  cameraServerRunning = false;
}

bool startCameraServer() {
  if (cameraServerRunning) {
    return true;
  }

  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.max_uri_handlers = 8;

  if (httpd_start(&cameraHttpd, &cfg) != ESP_OK) {
    Serial.println("[HTTP] Failed to start control server");
    cameraHttpd = nullptr;
    return false;
  }

  httpd_uri_t indexUri = {"/", HTTP_GET, indexHandler, nullptr};
  httpd_uri_t captureUri = {"/capture", HTTP_GET, captureHandler, nullptr};
  httpd_uri_t snapshotUri = {"/snapshot.jpg", HTTP_GET, captureHandler, nullptr};

  httpd_register_uri_handler(cameraHttpd, &indexUri);
  httpd_register_uri_handler(cameraHttpd, &captureUri);
  httpd_register_uri_handler(cameraHttpd, &snapshotUri);

  httpd_config_t streamCfg = HTTPD_DEFAULT_CONFIG();
  streamCfg.server_port = 81;
  streamCfg.ctrl_port = 32769;

  if (httpd_start(&streamHttpd, &streamCfg) != ESP_OK) {
    Serial.println("[HTTP] Failed to start stream server");
    stopCameraServer();
    return false;
  }

  httpd_uri_t streamUri = {"/stream", HTTP_GET, streamHandler, nullptr};
  httpd_register_uri_handler(streamHttpd, &streamUri);

  cameraServerRunning = true;
  Serial.println("[HTTP] Camera server started");
  Serial.printf("[HTTP] Snapshot: http://%s/capture\n", WiFi.localIP().toString().c_str());
  Serial.printf("[HTTP] Stream  : http://%s:81/stream\n", WiFi.localIP().toString().c_str());
  return true;
}

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = CAMERA_FRAME_SIZE;
    config.jpeg_quality = CAMERA_JPEG_QUALITY;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 18;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] Init failed 0x%x\n", err);
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_framesize(s, CAMERA_FRAME_SIZE);
  }

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);

  Serial.println("[CAM] Camera initialized");
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[BOOT] Outdoor ESP32-CAM firmware start");

  WiFi.onEvent(onWiFiEvent);
  WiFi.setSleep(false);
  delay(50);
  printScanForTarget();
  connectWiFiBlocking();

  if (!initCamera()) {
    Serial.println("[BOOT] Camera init failed. Rebooting in 5s...");
    delay(5000);
    ESP.restart();
  }
}

void loop() {
  maintainWiFiConnection();

  if (WiFi.status() == WL_CONNECTED) {
    if (!cameraServerRunning) {
      if (startCameraServer()) {
        String note = "boot ip=" + WiFi.localIP().toString() + " rssi=" + String(WiFi.RSSI());
        emitEvent("CAM_BOOT", 0.0f, "na", note);
      }
    }

    uint32_t now = millis();
    if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
      lastHeartbeatMs = now;
      String note = "ip=" + WiFi.localIP().toString() + " rssi=" + String(WiFi.RSSI()) + " stream=:81/stream";
      emitEvent("CAM_HEARTBEAT", 0.0f, "na", note);
    }
  } else {
    if (cameraServerRunning) {
      stopCameraServer();
      Serial.println("[WiFi] Disconnected. Camera server stopped.");
    }
  }

  processPendingEvent();
  delay(15);
}
