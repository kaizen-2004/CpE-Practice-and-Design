#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#include "espnow_packet.h"

/*
  ESP-NOW Gateway (ESP32)
  - Receives sensor packets over ESP-NOW
  - Emits one JSON line per packet over USB serial

  JSON format (serial output):
  {"node":"...","event":"...","room":"...","value":1.23,"unit":"...","note":"...","seq":123,"uptimeMs":4567,"rssi":-42,"src":"AA:BB:CC:DD:EE:FF"}
*/

static const uint8_t ESPNOW_CHANNEL = 6;
static const int STATUS_LED_PIN = 8;
static const bool STATUS_LED_ACTIVE_LOW = true;
static const uint32_t STATUS_PRINT_INTERVAL_MS = 30000;

struct RxQueueItem {
  EspNowSensorPacket pkt;
  int8_t rssi;
  uint8_t src[6];
};

static const uint8_t RX_QUEUE_CAPACITY = 24;
RxQueueItem rxQueue[RX_QUEUE_CAPACITY];
volatile uint8_t rxHead = 0;
volatile uint8_t rxTail = 0;
volatile uint32_t rawReceivedPackets = 0;
volatile uint32_t badLenPackets = 0;
volatile uint32_t badHeaderPackets = 0;
volatile uint32_t droppedPackets = 0;
volatile uint32_t receivedPackets = 0;

portMUX_TYPE rxMux = portMUX_INITIALIZER_UNLOCKED;

uint32_t lastStatusMs = 0;
uint32_t lastBlinkMs = 0;
bool ledState = false;

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

void pulseLed() {
  if (STATUS_LED_PIN < 0) {
    return;
  }
  setStatusLed(true);
  ledState = true;
  lastBlinkMs = millis();
}

void updateLed() {
  if (STATUS_LED_PIN < 0) {
    return;
  }
  if (ledState && (uint32_t)(millis() - lastBlinkMs) > 50) {
    setStatusLed(false);
    ledState = false;
  }
}

String jsonEscape(const char *in) {
  String out;
  if (!in) {
    return out;
  }

  size_t len = strlen(in);
  out.reserve(len + 8);
  for (size_t i = 0; i < len; ++i) {
    char c = in[i];
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

String macToString(const uint8_t mac[6]) {
  if (!mac) {
    return String("00:00:00:00:00:00");
  }
  char buf[18];
  snprintf(buf, sizeof(buf), "%02X:%02X:%02X:%02X:%02X:%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  return String(buf);
}

bool popPacket(RxQueueItem &out) {
  bool hasItem = false;

  portENTER_CRITICAL(&rxMux);
  if (rxTail != rxHead) {
    out = rxQueue[rxTail];
    rxTail = (uint8_t)((rxTail + 1) % RX_QUEUE_CAPACITY);
    hasItem = true;
  }
  portEXIT_CRITICAL(&rxMux);

  return hasItem;
}

void onEspNowRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  if (!info || !data) {
    return;
  }

  rawReceivedPackets++;

  if (len != (int)sizeof(EspNowSensorPacket)) {
    badLenPackets++;
    return;
  }

  EspNowSensorPacket pkt;
  memcpy(&pkt, data, sizeof(pkt));

  if (pkt.magic != ESPNOW_PACKET_MAGIC || pkt.version != ESPNOW_PACKET_VERSION || pkt.payloadSize != sizeof(pkt)) {
    badHeaderPackets++;
    return;
  }

  uint8_t nextHead;
  portENTER_CRITICAL_ISR(&rxMux);
  nextHead = (uint8_t)((rxHead + 1) % RX_QUEUE_CAPACITY);
  if (nextHead == rxTail) {
    droppedPackets++;
    portEXIT_CRITICAL_ISR(&rxMux);
    return;
  }

  rxQueue[rxHead].pkt = pkt;
  rxQueue[rxHead].rssi = (info->rx_ctrl) ? info->rx_ctrl->rssi : 0;
  if (info->src_addr) {
    memcpy(rxQueue[rxHead].src, info->src_addr, 6);
  } else {
    memset(rxQueue[rxHead].src, 0, 6);
  }

  rxHead = nextHead;
  receivedPackets++;
  portEXIT_CRITICAL_ISR(&rxMux);
}

void printPacketAsJson(const RxQueueItem &item) {
  String line;
  line.reserve(320);
  line += "{\"node\":\"" + jsonEscape(item.pkt.node) + "\"";
  line += ",\"event\":\"" + jsonEscape(item.pkt.event) + "\"";
  line += ",\"room\":\"" + jsonEscape(item.pkt.room) + "\"";
  line += ",\"value\":" + String(item.pkt.value, 3);
  line += ",\"unit\":\"" + jsonEscape(item.pkt.unit) + "\"";
  line += ",\"note\":\"" + jsonEscape(item.pkt.note) + "\"";
  line += ",\"seq\":" + String(item.pkt.seq);
  line += ",\"uptimeMs\":" + String(item.pkt.uptimeMs);
  line += ",\"rssi\":" + String(item.rssi);
  line += ",\"src\":\"" + macToString(item.src) + "\"";
  line += "}";

  Serial.println(line);
}

bool initEspNowGateway() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.disconnect();
  uint32_t wifiStartAt = millis();
  while (!WiFi.STA.started() && (uint32_t)(millis() - wifiStartAt) < 2000) {
    delay(10);
  }

  int chResult = WiFi.setChannel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (chResult != ESP_OK) {
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_wifi_set_promiscuous(false);
  }

  esp_now_deinit();
  if (esp_now_init() != ESP_OK) {
    Serial.println("[GATEWAY] ESP-NOW init failed");
    return false;
  }

  if (esp_now_register_recv_cb(onEspNowRecv) != ESP_OK) {
    Serial.println("[GATEWAY] ESP-NOW recv callback register failed");
    esp_now_deinit();
    return false;
  }

  Serial.printf("[GATEWAY] ESP-NOW ready cfg_ch=%u actual_ch=%u local_mac=%s\n",
                ESPNOW_CHANNEL,
                WiFi.channel(),
                WiFi.macAddress().c_str());
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  if (STATUS_LED_PIN >= 0) {
    pinMode(STATUS_LED_PIN, OUTPUT);
    setStatusLed(false);
  }

  Serial.println("\n[BOOT] ESP-NOW gateway start");

  if (!initEspNowGateway()) {
    Serial.println("[BOOT] gateway init failed; rebooting in 5s");
    delay(5000);
    ESP.restart();
  }

  lastStatusMs = millis();
}

void loop() {
  RxQueueItem item;
  while (popPacket(item)) {
    printPacketAsJson(item);
    pulseLed();
  }

  updateLed();

  uint32_t now = millis();
  if ((uint32_t)(now - lastStatusMs) >= STATUS_PRINT_INTERVAL_MS) {
    lastStatusMs = now;
    uint32_t raw = rawReceivedPackets;
    uint32_t rx = receivedPackets;
    uint32_t badLen = badLenPackets;
    uint32_t badHdr = badHeaderPackets;
    uint32_t drop = droppedPackets;
    Serial.printf("[GATEWAY] status ch=%u raw=%lu rx=%lu bad_len=%lu bad_hdr=%lu dropped=%lu\n",
                  WiFi.channel(),
                  (unsigned long)raw,
                  (unsigned long)rx,
                  (unsigned long)badLen,
                  (unsigned long)badHdr,
                  (unsigned long)drop);
  }

  delay(5);
}
