#include <WiFi.h>
#include <PubSubClient.h>

#include "../common/mqtt_payload.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

/*
  Smoke Node 1 (ESP32-C3 + MQ-2) via MQTT
  Node ID: mq2_living
*/

const char *NODE_ID = "mq2_living";
const char *ROOM_NAME = "Living Room";

static const int MQ2_ADC_PIN = 0;
static const int STATUS_LED_PIN = 8;
static const bool STATUS_LED_ACTIVE_LOW = true;

static const int ADC_SAMPLES = 8;
static const int ADC_HIGH_THRESHOLD = 2200;
static const int ADC_CLEAR_THRESHOLD = 1900;
static const uint8_t HIGH_CONFIRM_SAMPLES = 3;
static const uint8_t CLEAR_CONFIRM_SAMPLES = 5;

static const uint32_t SAMPLE_INTERVAL_MS = 1000;
static const uint32_t MIN_CRITICAL_EVENT_GAP_MS = 15000;
static const uint32_t EVENT_RETRY_INTERVAL_MS = 5000;
static const uint32_t WIFI_RETRY_INTERVAL_MS = 15000;
static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
static const uint32_t MQTT_RETRY_INTERVAL_MS = 5000;
static const uint16_t MQTT_KEEPALIVE_SECONDS = 120;
static const wifi_power_t WIFI_TX_POWER_LEVEL = WIFI_POWER_8_5dBm;

struct PendingEvent {
  bool active = false;
  String event;
  int value = 0;
  String note;
  uint32_t nextAttemptMs = 0;
};

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

char topicEvent[80];
char topicStatus[80];
char mqttClientId[48];

PendingEvent pendingEvent;

bool smokeLatched = false;
uint8_t highCount = 0;
uint8_t clearCount = 0;
uint32_t eventSeq = 0;

uint32_t lastSampleMs = 0;
uint32_t lastCriticalEventMs = 0;
uint32_t lastWiFiAttemptMs = 0;
uint32_t lastWiFiBeginMs = 0;
uint32_t lastMqttAttemptMs = 0;

void setStatusLed(bool on) {
  if (STATUS_LED_PIN < 0) return;
  int level = on ? HIGH : LOW;
  if (STATUS_LED_ACTIVE_LOW) level = on ? LOW : HIGH;
  digitalWrite(STATUS_LED_PIN, level);
}

void updateLedPattern() {
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
  char payload[180];
  mqttBuildStatusPayload(payload, sizeof(payload), online ? 1 : 0, WiFi.RSSI(), mqttNextSeq(eventSeq), note);
  return mqttClient.publish(topicStatus, payload, true);
}

bool publishEvent(const String &eventName, int value, const String &note) {
  if (!mqttClient.connected()) return false;
  char payload[220];
  mqttBuildEventPayload(
      payload,
      sizeof(payload),
      eventName.c_str(),
      (float)value,
      "adc",
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
      1,
      true,
      willPayload);

  if (ok) {
    publishStatus(true, "boot");
    Serial.println("[MQTT] connected");
  } else {
    Serial.printf("[MQTT] connect failed rc=%d\n", mqttClient.state());
  }
}

void queuePending(const String &eventName, int value, const String &note) {
  pendingEvent.active = true;
  pendingEvent.event = eventName;
  pendingEvent.value = value;
  pendingEvent.note = note;
  pendingEvent.nextAttemptMs = 0;
}

void emitEvent(const String &eventName, int value, const String &note, bool highPriority) {
  if (pendingEvent.active && !highPriority) return;
  if (pendingEvent.active && highPriority) pendingEvent.active = false;

  if (!publishEvent(eventName, value, note)) {
    queuePending(eventName, value, note);
  } else {
    Serial.printf("[MQTT] sent %s v=%d\n", eventName.c_str(), value);
  }
}

void processPendingEvent() {
  if (!pendingEvent.active) return;
  uint32_t now = millis();
  if (now < pendingEvent.nextAttemptMs) return;

  if (publishEvent(pendingEvent.event, pendingEvent.value, pendingEvent.note)) {
    pendingEvent.active = false;
    Serial.printf("[MQTT] retry sent %s\n", pendingEvent.event.c_str());
    return;
  }
  pendingEvent.nextAttemptMs = now + EVENT_RETRY_INTERVAL_MS;
}

int readMq2Raw() {
  long sum = 0;
  for (int i = 0; i < ADC_SAMPLES; ++i) {
    sum += analogRead(MQ2_ADC_PIN);
    delay(2);
  }
  return (int)(sum / ADC_SAMPLES);
}

void setup() {
  Serial.begin(115200);
  delay(250);
  Serial.println("\n[BOOT] Smoke Node 1 MQTT started");

  if (STATUS_LED_PIN >= 0) {
    pinMode(STATUS_LED_PIN, OUTPUT);
    setStatusLed(false);
  }

  analogReadResolution(12);
  analogSetPinAttenuation(MQ2_ADC_PIN, ADC_11db);

  snprintf(mqttClientId, sizeof(mqttClientId), "%s-client", NODE_ID);
  mqttTopicEvent(topicEvent, sizeof(topicEvent), MQTT_TOPIC_ROOT, NODE_ID);
  mqttTopicStatus(topicStatus, sizeof(topicStatus), MQTT_TOPIC_ROOT, NODE_ID);
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
  updateLedPattern();

  uint32_t now = millis();
  if ((uint32_t)(now - lastSampleMs) >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;
    int raw = readMq2Raw();

    if (raw >= ADC_HIGH_THRESHOLD) {
      highCount++;
      clearCount = 0;
    } else if (raw <= ADC_CLEAR_THRESHOLD) {
      clearCount++;
      highCount = 0;
    } else {
      highCount = 0;
      clearCount = 0;
    }

    if (!smokeLatched && highCount >= HIGH_CONFIRM_SAMPLES) {
      smokeLatched = true;
      highCount = 0;
      if ((uint32_t)(now - lastCriticalEventMs) >= MIN_CRITICAL_EVENT_GAP_MS) {
        emitEvent("SMOKE_HIGH", raw, "threshold_crossed", true);
        publishStatus(true, "latched=1");
        lastCriticalEventMs = now;
      }
    }

    if (smokeLatched && clearCount >= CLEAR_CONFIRM_SAMPLES) {
      smokeLatched = false;
      clearCount = 0;
      emitEvent("SMOKE_NORMAL", raw, "returned_below_clear_threshold", false);
      publishStatus(true, "latched=0");
    }
  }

  processPendingEvent();
  delay(15);
}
