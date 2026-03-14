#include "esp_camera.h"
#include "img_converters.h"
#include "esp_http_server.h"

#include <WiFi.h>
#include <PubSubClient.h>

#include "../common/mqtt_payload.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

/*
  Outdoor Camera Node (ESP32-CAM AI Thinker) with MQTT status/control

  - MJPEG stream:   http://<device-ip>:81/stream
  - Snapshot still: http://<device-ip>/capture
  - MQTT: events/status/control/ack
*/

const char *WIFI_HOSTNAME = "cam-outdoor";
const char *NODE_ID = "cam_outdoor";
const char *ROOM_NAME = "Door Entrance Area";

static const framesize_t CAMERA_FRAME_SIZE = FRAMESIZE_VGA;
static const int CAMERA_JPEG_QUALITY = 12;
static const uint32_t STREAM_FRAME_DELAY_MS = 70;

static const uint32_t WIFI_RETRY_INTERVAL_MS = 15000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
static const uint32_t MQTT_RETRY_INTERVAL_MS = 5000;
static const uint32_t HEARTBEAT_INTERVAL_MS = 30000;

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

static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
static const char *STREAM_BOUNDARY = "\r\n--frame\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t cameraHttpd = nullptr;
httpd_handle_t streamHttpd = nullptr;
bool cameraServerRunning = false;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

char topicEvent[80];
char topicStatus[80];
char topicControl[96];
char topicAck[80];
char mqttClientId[48];

uint32_t eventSeq = 0;
uint32_t lastWiFiReconnectAttemptAt = 0;
uint32_t lastWiFiBeginAt = 0;
uint32_t lastMqttAttemptAt = 0;
uint32_t lastHeartbeatMs = 0;

String jsonEscape(const String &in) {
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

const char *wifiStatusText(wl_status_t s) {
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
    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      Serial.printf("[WiFi] connected ip=%s rssi=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
      break;
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
      Serial.printf("[WiFi] disconnected reason=%d status=%s\n",
                    info.wifi_sta_disconnected.reason,
                    wifiStatusText(WiFi.status()));
      break;
    default:
      break;
  }
}

void beginWiFiConnection() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.setHostname(WIFI_HOSTNAME);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWiFiBeginAt = millis();
}

void maintainWiFiConnection() {
  if (WiFi.status() == WL_CONNECTED) return;
  uint32_t now = millis();
  if (WiFi.status() == WL_IDLE_STATUS && (uint32_t)(now - lastWiFiBeginAt) < WIFI_CONNECT_TIMEOUT_MS) {
    return;
  }
  if ((uint32_t)(now - lastWiFiReconnectAttemptAt) < WIFI_RETRY_INTERVAL_MS) return;
  lastWiFiReconnectAttemptAt = now;
  WiFi.disconnect();
  delay(20);
  beginWiFiConnection();
  Serial.printf("[WiFi] reconnect attempt ssid=%s\n", WIFI_SSID);
}

bool mqttPublishStatus(bool online, const String &note) {
  if (!mqttClient.connected()) return false;
  char payload[220];
  mqttBuildStatusPayload(payload, sizeof(payload), online ? 1 : 0, WiFi.RSSI(), mqttNextSeq(eventSeq), note.c_str());
  return mqttClient.publish(topicStatus, payload, true);
}

bool mqttPublishEvent(const String &eventName, float value, const String &unit, const String &note) {
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

void mqttPublishAck(const String &ok, const String &note) {
  if (!mqttClient.connected()) return;
  String payload = String("{\"v\":1,\"ok\":") + ok + ",\"q\":" + String(mqttNextSeq(eventSeq)) +
                   ",\"m\":\"" + jsonEscape(note) + "\"}";
  mqttClient.publish(topicAck, payload.c_str(), false);
}

String extractCmd(const String &raw) {
  String s = raw;
  s.trim();
  if (!s.length()) return "";
  if (!s.startsWith("{")) {
    s.toLowerCase();
    return s;
  }
  int k = s.indexOf("\"cmd\"");
  if (k < 0) return "";
  int colon = s.indexOf(':', k);
  if (colon < 0) return "";
  int q1 = s.indexOf('"', colon + 1);
  if (q1 < 0) return "";
  int q2 = s.indexOf('"', q1 + 1);
  if (q2 < 0) return "";
  String cmd = s.substring(q1 + 1, q2);
  cmd.trim();
  cmd.toLowerCase();
  return cmd;
}

void onMqttMessage(char *topic, byte *payload, unsigned int len) {
  if (String(topic) != String(topicControl)) return;
  String body;
  body.reserve(len + 1);
  for (unsigned int i = 0; i < len; ++i) body += (char)payload[i];
  String cmd = extractCmd(body);
  if (!cmd.length()) {
    mqttPublishAck("0", "invalid_command");
    return;
  }

  if (cmd == "reboot") {
    mqttPublishAck("1", "rebooting");
    delay(150);
    ESP.restart();
    return;
  }
  if (cmd == "flash_on") {
    digitalWrite(FLASH_LED_PIN, HIGH);
    mqttPublishAck("1", "flash_on");
    return;
  }
  if (cmd == "flash_off") {
    digitalWrite(FLASH_LED_PIN, LOW);
    mqttPublishAck("1", "flash_off");
    return;
  }
  if (cmd == "status") {
    mqttPublishStatus(true, "status_requested");
    mqttPublishAck("1", "status_published");
    return;
  }

  mqttPublishAck("0", "unsupported_command");
}

void maintainMqttConnection() {
  if (mqttClient.connected() || WiFi.status() != WL_CONNECTED) return;
  uint32_t now = millis();
  if ((uint32_t)(now - lastMqttAttemptAt) < MQTT_RETRY_INTERVAL_MS) return;
  lastMqttAttemptAt = now;

  mqttClient.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
  mqttClient.setCallback(onMqttMessage);
  mqttClient.setKeepAlive(30);

  char willPayload[120];
  mqttBuildStatusPayload(willPayload, sizeof(willPayload), 0, 0, 0, "offline");

  bool ok = mqttClient.connect(
      mqttClientId,
      MQTT_USERNAME,
      MQTT_PASSWORD,
      topicStatus,
      2,
      true,
      willPayload);

  if (ok) {
    mqttClient.subscribe(topicControl, 1);
    mqttPublishStatus(true, "mqtt_connected");
    mqttPublishEvent("CAM_BOOT", 0.0f, "na", String("ip=") + WiFi.localIP().toString());
    Serial.println("[MQTT] connected");
  } else {
    Serial.printf("[MQTT] connect failed rc=%d\n", mqttClient.state());
  }
}

esp_err_t indexHandler(httpd_req_t *req) {
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

esp_err_t captureHandler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  esp_err_t res = httpd_resp_send(req, reinterpret_cast<const char *>(fb->buf), fb->len);
  esp_camera_fb_return(fb);
  return res;
}

esp_err_t streamHandler(httpd_req_t *req) {
  esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  camera_fb_t *fb = nullptr;
  uint8_t *jpgBuf = nullptr;
  size_t jpgLen = 0;
  char partBuf[64];

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      res = ESP_FAIL;
    } else {
      if (fb->format != PIXFORMAT_JPEG) {
        bool ok = frame2jpg(fb, CAMERA_JPEG_QUALITY, &jpgBuf, &jpgLen);
        esp_camera_fb_return(fb);
        fb = nullptr;
        if (!ok) res = ESP_FAIL;
      } else {
        jpgBuf = fb->buf;
        jpgLen = fb->len;
      }
    }

    if (res == ESP_OK) {
      size_t hlen = snprintf(partBuf, sizeof(partBuf), STREAM_PART, jpgLen);
      res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
      if (res == ESP_OK) res = httpd_resp_send_chunk(req, partBuf, hlen);
      if (res == ESP_OK) res = httpd_resp_send_chunk(req, reinterpret_cast<const char *>(jpgBuf), jpgLen);
    }

    if (fb) {
      esp_camera_fb_return(fb);
      fb = nullptr;
      jpgBuf = nullptr;
    } else if (jpgBuf) {
      free(jpgBuf);
      jpgBuf = nullptr;
    }

    if (res != ESP_OK) break;
    delay(STREAM_FRAME_DELAY_MS);
  }
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
  if (cameraServerRunning) return true;

  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.max_uri_handlers = 8;
  if (httpd_start(&cameraHttpd, &cfg) != ESP_OK) {
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
    stopCameraServer();
    return false;
  }
  httpd_uri_t streamUri = {"/stream", HTTP_GET, streamHandler, nullptr};
  httpd_register_uri_handler(streamHttpd, &streamUri);

  cameraServerRunning = true;
  Serial.printf("[HTTP] stream=http://%s:81/stream\n", WiFi.localIP().toString().c_str());
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
    Serial.printf("[CAM] init failed err=0x%x\n", err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_framesize(s, CAMERA_FRAME_SIZE);
  }

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(250);
  Serial.println("\n[BOOT] cam_outdoor MQTT start");

  snprintf(mqttClientId, sizeof(mqttClientId), "%s-client", NODE_ID);
  mqttTopicEvent(topicEvent, sizeof(topicEvent), MQTT_TOPIC_ROOT, NODE_ID);
  mqttTopicStatus(topicStatus, sizeof(topicStatus), MQTT_TOPIC_ROOT, NODE_ID);
  mqttTopicCameraControl(topicControl, sizeof(topicControl), MQTT_TOPIC_ROOT, NODE_ID);
  mqttTopicCameraAck(topicAck, sizeof(topicAck), MQTT_TOPIC_ROOT, NODE_ID);

  WiFi.onEvent(onWiFiEvent);
  WiFi.setSleep(false);
  beginWiFiConnection();

  if (!initCamera()) {
    Serial.println("[BOOT] camera init failed; rebooting");
    delay(4000);
    ESP.restart();
  }
}

void loop() {
  maintainWiFiConnection();

  if (WiFi.status() == WL_CONNECTED) {
    if (!cameraServerRunning) startCameraServer();
    maintainMqttConnection();
    mqttClient.loop();

    uint32_t now = millis();
    if (lastHeartbeatMs == 0 || (uint32_t)(now - lastHeartbeatMs) >= HEARTBEAT_INTERVAL_MS) {
      lastHeartbeatMs = now;
      String note = "ip=" + WiFi.localIP().toString() + " stream=:81/stream";
      mqttPublishStatus(true, note);
      mqttPublishEvent("CAM_HEARTBEAT", 0.0f, "na", note);
    }
  } else {
    if (cameraServerRunning) {
      stopCameraServer();
    }
  }

  delay(15);
}
