// RobotCompanion v1 — Wokwi logic test
// Real parts simulated: ESP32-S3, MPU6050 (I2C), HC-SR04.
// LEDs stand in for the PCA9685 -> TB6612 -> motor chain (not in Wokwi's library).
// Pin numbers here are placeholders: re-map to the Guition board's free GPIOs once confirmed.

#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

const int I2C_SDA = 8;
const int I2C_SCL = 9;
const int SONAR_TRIG = 4;
const int SONAR_ECHO = 5;
const int MOTOR_L = 6;
const int MOTOR_R = 7;
const int WARN_LED = 15;

const float OBSTACLE_CM = 20.0;
const float TILT_LIMIT_DEG = 30.0;

Adafruit_MPU6050 imu;

float readDistanceCm() {
  digitalWrite(SONAR_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(SONAR_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(SONAR_TRIG, LOW);
  long us = pulseIn(SONAR_ECHO, HIGH, 30000);
  if (us == 0) return 999.0;
  return us / 58.0;
}

float readTiltDeg() {
  sensors_event_t a, g, t;
  imu.getEvent(&a, &g, &t);
  float roll  = atan2(a.acceleration.y, a.acceleration.z) * 180.0 / PI;
  float pitch = atan2(-a.acceleration.x,
                      sqrt(a.acceleration.y * a.acceleration.y + a.acceleration.z * a.acceleration.z)) * 180.0 / PI;
  return max(fabs(roll), fabs(pitch));
}

void setMotors(bool left, bool right) {
  digitalWrite(MOTOR_L, left);
  digitalWrite(MOTOR_R, right);
}

void setup() {
  Serial.begin(115200);
  pinMode(SONAR_TRIG, OUTPUT);
  pinMode(SONAR_ECHO, INPUT);
  pinMode(MOTOR_L, OUTPUT);
  pinMode(MOTOR_R, OUTPUT);
  pinMode(WARN_LED, OUTPUT);

  Wire.begin(I2C_SDA, I2C_SCL);
  if (!imu.begin()) {
    Serial.println("MPU6050 not found — check SDA/SCL wiring");
    while (true) delay(1000);
  }
  Serial.println("Robot brain online");
}

void loop() {
  float dist = readDistanceCm();
  float tilt = readTiltDeg();

  if (tilt > TILT_LIMIT_DEG) {
    setMotors(false, false);
    digitalWrite(WARN_LED, HIGH);
    Serial.printf("TIPPING (%.0f deg) — motors stopped\n", tilt);
  } else if (dist < OBSTACLE_CM) {
    setMotors(true, false);
    digitalWrite(WARN_LED, HIGH);
    Serial.printf("Obstacle at %.0f cm — turning\n", dist);
  } else {
    setMotors(true, true);
    digitalWrite(WARN_LED, LOW);
    Serial.printf("Clear (%.0f cm, tilt %.0f deg) — driving forward\n", dist, tilt);
  }
  delay(300);
}
