// display.cpp -- NV3041A 480x272 QSPI panel through Arduino_GFX, fed from two full RGB565 frames in
// PSRAM (double buffer): the face task renders frame N+1 while the push task sends frame N, and a
// frame is only ever sent complete, so there is no half-drawn face on screen.
//
// Why Arduino_GFX (not LovyanGFX) for this panel: Arduino_GFX ships a native NV3041A driver with an
// ESP32 QSPI data bus (Arduino_ESP32QSPI) -- the same driver the board vendor's demos use -- whereas
// LovyanGFX has no NV3041A panel class in the versions that build on Arduino-ESP32 2.x. All drawing
// happens in our own rasteriser (lib/spike_face), so the library is only a frame pusher.
#include "app.h"
#include "config.h"
#include <Arduino_GFX_Library.h>
#include <esp_heap_caps.h>

static Arduino_DataBus* bus;
static Arduino_GFX* gfx;
static uint16_t* frames[2];
static int back = 0;
static QueueHandle_t pushQ;       // index of a finished frame
static SemaphoreHandle_t freeSem[2];

static void pushTask(void*) {
  for (;;) {
    int idx;
    if (xQueueReceive(pushQ, &idx, portMAX_DELAY) != pdTRUE) continue;
    gfx->draw16bitRGBBitmap(0, 0, frames[idx], LCD_W, LCD_H);
    xSemaphoreGive(freeSem[idx]);
  }
}

void displayBegin() {
  bus = new Arduino_ESP32QSPI(PIN_LCD_CS, PIN_LCD_SCK, PIN_LCD_D0, PIN_LCD_D1, PIN_LCD_D2, PIN_LCD_D3);
  gfx = new Arduino_NV3041A(bus, GFX_NOT_DEFINED, 0 /* rotation */, true /* IPS */);
  if (!gfx->begin(LCD_SPEED_HZ)) logf("display: panel begin failed");
  gfx->fillScreen(0x0000);
  ledcSetup(0, 5000, 8);
  ledcAttachPin(PIN_LCD_BL, 0);
  displayBacklight(255);
  for (int i = 0; i < 2; i++) {
    frames[i] = (uint16_t*)heap_caps_malloc(LCD_W * LCD_H * 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!frames[i]) logf("display: PSRAM frame %d allocation FAILED (is PSRAM enabled?)", i);
    freeSem[i] = xSemaphoreCreateBinary();
    xSemaphoreGive(freeSem[i]);
  }
  pushQ = xQueueCreate(2, sizeof(int));
  xTaskCreatePinnedToCore(pushTask, "push", 4096, nullptr, 3, nullptr, 0);
  xSemaphoreTake(freeSem[back], portMAX_DELAY);
  logf("display: NV3041A %dx%d QSPI @ %lu Hz, 2 PSRAM frames", LCD_W, LCD_H, (unsigned long)LCD_SPEED_HZ);
}

uint16_t* displayBackBuffer() { return frames[back]; }

void displayPresent() {
  int idx = back;
  xQueueSend(pushQ, &idx, portMAX_DELAY);
  back ^= 1;
  xSemaphoreTake(freeSem[back], portMAX_DELAY);  // wait until the panel has finished with it
}

void displayBacklight(uint8_t level) { ledcWrite(0, level); }
