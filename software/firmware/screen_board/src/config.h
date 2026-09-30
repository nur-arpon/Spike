// config.h -- every pin, address and tunable of the screen board in one place.
//
// Sources (see ../DESIGN.md "Pin map as used"):
//   * Guition JC4827W543C board pins: panel NV3041A on QSPI, GT911 touch, NS4168 amp -- the vendor
//     demo / Arduino_GFX board definition for this module (checked against the brief's "IO42/IO2/IO41").
//   * Robot wiring: MIRRORS guide/OPEN_QUESTIONS.md section D "Firmware pin and channel map", generated
//     from PINMAP in guide/src/data_wiring.py (the single source; guide/tools/servo_center uses the same).
//     The owner wires exactly the guide. tools/check_pinmap.py fails if this file and PINMAP disagree.
//     Servo / laser channels: lib/spike_body/src/spike_body.cpp kServoMap / kLaserMap.
#pragma once
#include <stdint.h>

// ---- display: NV3041A 480x272 over QSPI ------------------------------------------------------
#define PIN_LCD_CS 45
#define PIN_LCD_SCK 47
#define PIN_LCD_D0 21
#define PIN_LCD_D1 48
#define PIN_LCD_D2 40
#define PIN_LCD_D3 39
#define PIN_LCD_BL 1
#define LCD_SPEED_HZ 32000000UL   // NV3041A QSPI; vendor demos run 32 MHz
#define LCD_W 480
#define LCD_H 272

// ---- touch: GT911 on its own I2C bus (Wire1) --------------------------------------------------
#define PIN_TP_SDA 8
#define PIN_TP_SCL 4
#define PIN_TP_INT 3
#define PIN_TP_RST 38
#define TP_I2C_HZ 400000

// ---- audio ----------------------------------------------------------------------------------
// Onboard NS4168 class-D amp -> "Speak" port (brief: IO42 / IO2 / IO41)
#define PIN_SPK_BCLK 42
#define PIN_SPK_LRCK 2
#define PIN_SPK_DOUT 41
// 2 x MS3625 I2S mics on port P3 (guide S11/S12): SCK IO6, WS IO7, SD IO15; left mic L/R -> GND
#define PIN_MIC_SCK 6
#define PIN_MIC_WS 7
#define PIN_MIC_SD 15
#define SPEAKER_RATE 22050   // I2S out; offered to the brain first in hello.audio_out.rates
#define MIC_RATE 16000       // protocol 6.7: mono 16 kHz
#define MIC_CHUNK_MS 40      // protocol: 20..100 ms per chunk
#define MIC_MUTE_TAIL_MS 300 // BOM 2e: mute while speaking and 300 ms after

// ---- robot bus on port P4 (guide S1): I2C for both PCA9685, MPU6050, MPR121, APDS-9960, 7 lasers --
#define PIN_I2C_SDA 17
#define PIN_I2C_SCL 18
#define ROBOT_I2C_HZ 100000   // guide PINMAP: 100 kHz, one star-wired bus through the collar
#define PIN_SERVO_OE 14      // both PCA9685 OE; 2.2k pull-up to 3V3 -> HIGH = every output off
#define PIN_VBAT 5           // 10k (top) / 4.7k (bottom) divider from the switched battery
#define VBAT_DIVIDER ((10.0f + 4.7f) / 4.7f)

#define ADDR_MPU6050 0x68
#define ADDR_MPR121 0x5A
#define ADDR_APDS9960 0x39

// MPR121 electrodes (guide S10): E0 back-left, E1 back-right, E2 rump-left, E3 rump-right, E4 head
#define PAD_HEAD 4

// ---- timing ---------------------------------------------------------------------------------
#define FACE_FPS_TARGET 30
#define BODY_HZ 50
#define WDT_TIMEOUT_S 3      // task watchdog: reboot (OE floats high -> servos stop) if a task hangs
#define BODY_STALL_MS 300    // supervisor: OE high if the body task has not ticked for this long

// ---- network --------------------------------------------------------------------------------
#define BRAIN_DEFAULT_PORT 8765
#define SETUP_AP_PREFIX "Spike-Setup-"
#define WS_MAX_MESSAGE (70 * 1024)  // protocol: <= 64 KiB per message
