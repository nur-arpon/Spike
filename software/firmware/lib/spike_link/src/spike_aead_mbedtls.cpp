// spike_aead_mbedtls.cpp -- see spike_aead_mbedtls.h. Empty on the PC.
#include "spike_aead_mbedtls.h"

#if defined(ESP_PLATFORM) || defined(ARDUINO_ARCH_ESP32)
#include <mbedtls/gcm.h>
#include <string.h>

namespace spike {
namespace espnow {

namespace {
class MbedAead : public Aead {
 public:
  bool seal(const uint8_t key[kKeyLen], const uint8_t nonce[kNonceLen], const uint8_t* aad, size_t aadLen,
            const uint8_t* pt, size_t len, uint8_t* ct, uint8_t tag[kTagLen]) override {
    mbedtls_gcm_context g;
    mbedtls_gcm_init(&g);
    int rc = mbedtls_gcm_setkey(&g, MBEDTLS_CIPHER_ID_AES, key, kKeyLen * 8);
    if (rc == 0)
      rc = mbedtls_gcm_crypt_and_tag(&g, MBEDTLS_GCM_ENCRYPT, len, nonce, kNonceLen, aad, aadLen, pt, ct, kTagLen, tag);
    mbedtls_gcm_free(&g);
    return rc == 0;
  }
  bool open(const uint8_t key[kKeyLen], const uint8_t nonce[kNonceLen], const uint8_t* aad, size_t aadLen,
            const uint8_t* ct, size_t len, const uint8_t tag[kTagLen], uint8_t* pt) override {
    mbedtls_gcm_context g;
    mbedtls_gcm_init(&g);
    int rc = mbedtls_gcm_setkey(&g, MBEDTLS_CIPHER_ID_AES, key, kKeyLen * 8);
    if (rc == 0) rc = mbedtls_gcm_auth_decrypt(&g, len, nonce, kNonceLen, aad, aadLen, tag, kTagLen, ct, pt);
    mbedtls_gcm_free(&g);
    return rc == 0;  // MBEDTLS_ERR_GCM_AUTH_FAILED (and mbedTLS zeroes pt) when the tag is wrong
  }
};
}  // namespace

Aead& mbedtlsAead() {
  static MbedAead a;
  return a;
}

}  // namespace espnow
}  // namespace spike
#endif
