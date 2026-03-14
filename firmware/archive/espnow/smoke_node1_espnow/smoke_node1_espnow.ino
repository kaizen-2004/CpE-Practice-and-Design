#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#include "espnow_packet.h"

/*
  Smoke Node 1 (ESP32-C3 + MQ-2) via ESP-NOW
  Node ID: mq2_living
*/

const char *NODE_ID = "mq2_living";
const char *ROOM_NAME = "Living Room";

// ESP-NOW transport configuration
static const uint8_t ESPNOW_CHANNEL = 6;
static const bool ESPNOW_USE_BROADCAST = true;
static const uint8_t ESPNOW_GATEWAY_MAC[6] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x00}; // Used if ESPNOW_USE_BROADCAST=false
static const uint8_t ESPNOW_BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static const uint32_t ESPNOW_SEND_WAIT_MS = 80;
static const uint32_t ESPNOW_RETRY_INTERVAL_MS = 5000;

// Hardware pins
static const int MQ2_ADC_PIN = 0;
static const int STATUS_LED_PIN = 8;
static const bool STATUS_LED_ACTIVE_LOW = true;

// ADC + detection tuning
static const int ADC_SAMPLES = 8;
static const int ADC_HIGH_THRESHOLD = 2200;
static const int ADC_CLEAR_THRESHOLD = 1900;
static const uint8_t HIGH_CONFIRM_SAMPLES = 3;
static const uint8_t CLEAR_CONFIRM_SAMPLES = 5;

// Timing
static const uint32_t SAMPLE_INTERVAL_MS = 1000;
static const uint32_t HEARTBEAT_INTERVAL_MS = 15000;
static const uint32_t MIN_CRITICAL_EVENT_GAP_MS = 15000;
static const uint32_t EVENT_RETRY_INTERVAL_MS = 5000;

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
uint32_t lastEspNowInitAttemptMs = 0;
uint32_t eventSeq = 0;

bool espNowReady = false;
volatile bool sendCallbackDone = false;
volatile esp_now_send_status_t sendCallbackStatus = ESP_NOW_SEND_FAIL;

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
  if (espNowReady) {
    setStatusLed(true);
    return;
  }
  bool blinkOn = ((millis() / 300) % 2) == 0;
  setStatusLed(blinkOn);
}

void peerAddress(uint8_t out[6]) {
  if (ESPNOW_USE_BROADCAST) {
    memcpy(out, ESPNOW_BROADCAST_MAC, 6);
  } else {
    memcpy(out, ESPNOW_GATEWAY_MAC, 6);
  }
}

void onEspNowSent(const esp_now_send_info_t *txInfo, esp_now_send_status_t status) {
  (void)txInfo;
  sendCallbackStatus = status;
  sendCallbackDone = true;
}

bool initEspNow() {
  if (espNowReady) {
    return true;
  }

  uint32_t now = millis();
  if ((uint32_t)(now - lastEspNowInitAttemptMs) < ESPNOW_RETRY_INTERVAL_MS) {
    return false;
  }
  lastEspNowInitAttemptMs = now;

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.disconnect();
  delay(20);

  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);

  esp_now_deinit();
  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESPNOW] init failed");
    return false;
  }

  if (esp_now_register_send_cb(onEspNowSent) != ESP_OK) {
    Serial.println("[ESPNOW] send callback register failed");
    esp_now_deinit();
    return false;
  }

  esp_now_peer_info_t peerInfo = {};
  peerAddress(peerInfo.peer_addr);
  peerInfo.channel = ESPNOW_CHANNEL;
  peerInfo.encrypt = false;

  esp_err_t peerErr = esp_now_add_peer(&peerInfo);
  if (peerErr != ESP_OK && peerErr != ESP_ERR_ESPNOW_EXIST) {
    Serial.printf("[ESPNOW] add peer failed err=%d\n", (int)peerErr);
    esp_now_deinit();
    return false;
  }

  espNowReady = true;
  Serial.printf("[ESPNOW] ready ch=%u mode=%s local_mac=%s\n",
                ESPNOW_CHANNEL,
                ESPNOW_USE_BROADCAST ? "broadcast" : "unicast",
                WiFi.macAddress().c_str());
  return true;
}

void maintainEspNow() {
  if (!espNowReady) {
    initEspNow();
  }
}

bool sendPacketNow(EspNowSensorPacket &pkt) {
  if (!espNowReady) {
    return false;
  }

  uint8_t destAddr[6];
  peerAddress(destAddr);

  sendCallbackDone = false;
  sendCallbackStatus = ESP_NOW_SEND_FAIL;

  esp_err_t err = esp_now_send(destAddr, reinterpret_cast<const uint8_t *>(&pkt), sizeof(pkt));
  if (err != ESP_OK) {
    Serial.printf("[ESPNOW] send enqueue failed err=%d\n", (int)err);
    if (err == ESP_ERR_ESPNOW_NOT_INIT || err == ESP_ERR_ESPNOW_INTERNAL) {
      espNowReady = false;
    }
    return false;
  }

  uint32_t startedAt = millis();
  while (!sendCallbackDone && (uint32_t)(millis() - startedAt) < ESPNOW_SEND_WAIT_MS) {
    delay(1);
  }

  if (!sendCallbackDone) {
    Serial.println("[ESPNOW] send timeout");
    return false;
  }

  bool ok = (sendCallbackStatus == ESP_NOW_SEND_SUCCESS);
  if (!ok) {
    Serial.printf("[ESPNOW] send status=%d\n", (int)sendCallbackStatus);
  }
  return ok;
}

bool sendEventNow(const String &eventName, int value, const String &note) {
  EspNowSensorPacket pkt;
  initEspNowPacket(pkt);

  pkt.seq = ++eventSeq;
  pkt.uptimeMs = millis();
  pkt.value = (float)value;

  espnowSafeCopy(pkt.node, sizeof(pkt.node), NODE_ID);
  espnowSafeCopy(pkt.room, sizeof(pkt.room), ROOM_NAME);
  espnowSafeCopy(pkt.event, sizeof(pkt.event), eventName.c_str());
  espnowSafeCopy(pkt.unit, sizeof(pkt.unit), "adc_raw");
  espnowSafeCopy(pkt.note, sizeof(pkt.note), note.c_str());

  bool ok = sendPacketNow(pkt);
  if (ok) {
    Serial.printf("[ESPNOW] %s sent seq=%lu\n", eventName.c_str(), (unsigned long)pkt.seq);
  }
  return ok;
}

void queuePending(const String &eventName, int value, const String &note) {
  pendingEvent.active = true;
  pendingEvent.event = eventName;
  pendingEvent.value = value;
  pendingEvent.note = note;
  pendingEvent.nextAttemptMs = 0;
}

void emitEvent(const String &eventName, int value, const String &note, bool highPriority) {
  if (pendingEvent.active && !highPriority) {
    return;
  }

  if (pendingEvent.active && highPriority) {
    pendingEvent.active = false;
  }

  if (!sendEventNow(eventName, value, note)) {
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

  if (sendEventNow(pendingEvent.event, pendingEvent.value, pendingEvent.note)) {
    pendingEvent.active = false;
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
  return static_cast<int>(sum / ADC_SAMPLES);
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

  Serial.println("\n[BOOT] Smoke Node 1 ESP-NOW started");
  Serial.printf("[BOOT] node=%s room=%s pin=%d\n", NODE_ID, ROOM_NAME, MQ2_ADC_PIN);

  initEspNow();
}

void loop() {
  maintainEspNow();
  updateLedPattern();

  uint32_t now = millis();

  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;

    int raw = readMq2Raw();
    Serial.printf("[SAMPLE] adc=%d latched=%d espnow=%d\n", raw, smokeLatched ? 1 : 0, espNowReady ? 1 : 0);

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

      if (now - lastCriticalEventMs >= MIN_CRITICAL_EVENT_GAP_MS) {
        emitEvent("SMOKE_HIGH", raw, "threshold_crossed", true);
        lastCriticalEventMs = now;
      }
    }

    if (smokeLatched && clearCount >= CLEAR_CONFIRM_SAMPLES) {
      smokeLatched = false;
      clearCount = 0;
      emitEvent("SMOKE_NORMAL", raw, "returned_below_clear_threshold", false);
    }

    if (lastHeartbeatMs == 0 || now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
      String note = "link=espnow latched=" + String(smokeLatched ? 1 : 0);
      emitEvent("SMOKE_HEARTBEAT", raw, note, false);
      lastHeartbeatMs = now;
    }
  }

  processPendingEvent();
  delay(15);
}
