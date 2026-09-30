// spike_aead_mbedtls.h -- AES-256-GCM for the ESP-NOW hand-over on the ESP32 boards (mbedTLS from
// ESP-IDF, hardware AES). Only compiled for the ESP32; the PC test has its own Aead (Windows CNG).
#pragma once
#include "spike_espnow_pkt.h"

#if defined(ESP_PLATFORM) || defined(ARDUINO_ARCH_ESP32)
namespace spike {
namespace espnow {
Aead& mbedtlsAead();  // stateless, safe to call from any task
}  // namespace espnow
}  // namespace spike
#endif
