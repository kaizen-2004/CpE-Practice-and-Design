#pragma once

#include <stdint.h>
#include <string.h>

// Shared packet schema for ESP-NOW sensor nodes and the ESP-NOW gateway.
// Keep this structure <= 250 bytes (ESP-NOW payload limit).
static const uint32_t ESPNOW_PACKET_MAGIC = 0x45534E57; // "ESNW"
static const uint8_t ESPNOW_PACKET_VERSION = 1;

struct __attribute__((packed)) EspNowSensorPacket {
  uint32_t magic;
  uint8_t version;
  uint8_t reserved;
  uint16_t payloadSize;
  uint32_t seq;
  uint32_t uptimeMs;
  char node[20];
  char room[24];
  char event[24];
  char unit[16];
  float value;
  char note[72];
};

inline void espnowSafeCopy(char *dst, size_t dstSize, const char *src) {
  if (!dst || dstSize == 0) {
    return;
  }
  if (!src) {
    dst[0] = '\0';
    return;
  }
  strncpy(dst, src, dstSize - 1);
  dst[dstSize - 1] = '\0';
}

inline void initEspNowPacket(EspNowSensorPacket &pkt) {
  memset(&pkt, 0, sizeof(pkt));
  pkt.magic = ESPNOW_PACKET_MAGIC;
  pkt.version = ESPNOW_PACKET_VERSION;
  pkt.payloadSize = (uint16_t)sizeof(pkt);
}
