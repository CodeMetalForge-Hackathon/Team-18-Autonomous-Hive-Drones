#pragma once
#include <stdint.h>

struct RangeReading {
  bool valid;
  uint16_t mm;
  uint32_t timestamp;
};

// Local obstacle avoidance only: no camera, laptop, map, or learned position.
class Navigator {
 public:
  enum State { Off, Forward, Pause, Turn, SensorFault, Blocked };
  State state = Off;
  uint32_t entered = 0;
  uint32_t turnStarted = 0;
  uint32_t lastClearTimestamp = 0;
  unsigned clearSamples = 0;

  static bool usable(uint32_t now, RangeReading range) {
    return range.valid && range.mm >= 30 && range.mm <= 5000 &&
           uint32_t(now - range.timestamp) <= 200;
  }
  bool start(uint32_t now, RangeReading range) {
    stop();
    if (!usable(now, range)) { state = SensorFault; return false; }
    state = Pause;
    entered = now;
    return true;
  }
  void stop() { state = Off; clearSamples = 0; }
  bool active() const { return state == Forward || state == Pause || state == Turn; }
  char update(uint32_t now, RangeReading range) {
    if (!active()) return 'S';
    if (!usable(now, range)) { state = SensorFault; return 'S'; }
    if (state == Forward) {
      if (range.mm <= 300) {
        state = Pause; entered = now; clearSamples = 0;
        return 'S';
      }
      return 'F';
    }
    if (state == Pause) {
      if (uint32_t(now - entered) < 200) return 'S';
      if (range.mm >= 500) { state = Forward; return 'F'; }
      state = Turn; entered = turnStarted = now;
      lastClearTimestamp = range.timestamp; clearSamples = 0;
    }
    if (uint32_t(now - turnStarted) >= 3000) { state = Blocked; return 'S'; }
    if (range.timestamp != lastClearTimestamp) {
      lastClearTimestamp = range.timestamp;
      clearSamples = range.mm >= 500 ? clearSamples + 1 : 0;
    }
    if (clearSamples >= 2) { state = Pause; entered = now; return 'S'; }
    // Short rotation pulses with a pause to obtain a fresh distance sample.
    return uint32_t(now - entered) % 240 < 120 ? 'E' : 'S';
  }
};
