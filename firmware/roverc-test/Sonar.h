#pragma once
#include "Navigator.h"

// Seeed Grove Ultrasonic Ranger: trigger and echo share yellow/SIG.
// GPIO33 is verified with the connected Grove sensor and cable on this rover.
// Set ROVER_SONAR_PIN=-1 for hardware without this sensor.
#ifndef ROVER_SONAR_PIN
#define ROVER_SONAR_PIN 33
#endif
class Sonar {
 public:
  static constexpr int signalPin = ROVER_SONAR_PIN;
  static constexpr bool configured = signalPin >= 0;
  unsigned long echoMicroseconds() const { return lastEcho; }
  void begin() { if (configured) pinMode(signalPin, INPUT); }
  RangeReading read(uint32_t now) {
    if (!configured) return {false, 0, now};
    if (attempted && uint32_t(now-lastAttempt) < 60) return latest;
    attempted = true;
    lastAttempt = now;
    pinMode(signalPin, OUTPUT);
    digitalWrite(signalPin, LOW); delayMicroseconds(2);
    digitalWrite(signalPin, HIGH); delayMicroseconds(20);
    digitalWrite(signalPin, LOW);
    pinMode(signalPin, INPUT);
    unsigned long duration = pulseIn(signalPin, HIGH, 25000);
    lastEcho = duration;
    uint32_t mm = (duration * 340UL + 1000) / 2000;
    bool valid = duration > 0 && mm >= 20 && mm <= 3500;
    latest = {valid, uint16_t(valid ? mm : 0), millis()};
    return latest;
  }
 private:
  bool attempted = false;
  unsigned long lastEcho = 0;
  uint32_t lastAttempt = 0;
  RangeReading latest = {false, 0, 0};
};
