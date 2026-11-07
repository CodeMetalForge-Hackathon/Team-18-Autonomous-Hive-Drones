#pragma once
#include "Navigator.h"

// Replace only after the physical sonar model, signal voltage and pins are known.
// Invalid readings deliberately prevent autonomous movement.
class Sonar {
 public:
  static constexpr bool configured = false;
  void begin() {}
  RangeReading read(uint32_t now) { return {false, 0, now}; }
};
