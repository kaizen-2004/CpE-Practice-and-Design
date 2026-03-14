#pragma once

#include <Arduino.h>
#include <stdio.h>
#include <string.h>

inline uint32_t mqttNextSeq(uint32_t &seq) {
  seq += 1;
  return seq;
}

inline void mqttBuildEventPayload(
    char *out,
    size_t out_size,
    const char *event_name,
    float value,
    const char *unit,
    uint32_t seq,
    const char *note,
    const char *room) {
  if (!out || out_size == 0) {
    return;
  }
  const char *u = unit ? unit : "";
  const char *m = note ? note : "";
  const char *r = room ? room : "";
  snprintf(
      out,
      out_size,
      "{\"v\":1,\"e\":\"%s\",\"x\":%.4f,\"u\":\"%s\",\"q\":%lu,\"m\":\"%s\",\"room\":\"%s\"}",
      event_name ? event_name : "",
      value,
      u,
      (unsigned long)seq,
      m,
      r);
}

inline void mqttBuildStatusPayload(
    char *out,
    size_t out_size,
    int online,
    int rssi,
    uint32_t seq,
    const char *note) {
  if (!out || out_size == 0) {
    return;
  }
  const char *m = note ? note : "";
  snprintf(
      out,
      out_size,
      "{\"v\":1,\"s\":%d,\"r\":%d,\"q\":%lu,\"m\":\"%s\"}",
      online ? 1 : 0,
      rssi,
      (unsigned long)seq,
      m);
}

inline void mqttTopicEvent(char *out, size_t out_size, const char *topic_root, const char *node_id) {
  snprintf(out, out_size, "%s/events/%s", topic_root, node_id);
}

inline void mqttTopicStatus(char *out, size_t out_size, const char *topic_root, const char *node_id) {
  snprintf(out, out_size, "%s/status/%s", topic_root, node_id);
}

inline void mqttTopicCameraControl(char *out, size_t out_size, const char *topic_root, const char *node_id) {
  snprintf(out, out_size, "%s/camera/%s/control", topic_root, node_id);
}

inline void mqttTopicCameraAck(char *out, size_t out_size, const char *topic_root, const char *node_id) {
  snprintf(out, out_size, "%s/camera/%s/ack", topic_root, node_id);
}
