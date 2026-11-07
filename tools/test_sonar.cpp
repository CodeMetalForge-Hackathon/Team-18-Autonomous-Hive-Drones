#include <cassert>
#include <cstdint>
constexpr int INPUT=0, OUTPUT=1, LOW=0, HIGH=1;
uint32_t nowMs=0;
unsigned long echo=1000;
int triggers=0;
void pinMode(int, int) {}
void digitalWrite(int, int value) { if (value==HIGH) ++triggers; }
void delayMicroseconds(unsigned int) {}
unsigned long pulseIn(int pin, int value, unsigned long timeout) {
  assert(pin==33 && value==HIGH && timeout==25000); return echo;
}
uint32_t millis() { return nowMs; }
#include "../firmware/roverc-test/Sonar.h"
int main() {
  Sonar sonar;
  sonar.begin();
  auto first=sonar.read(0);
  assert(first.valid && first.mm==170 && triggers==1);
  nowMs=20; echo=0;
  assert(sonar.read(nowMs).valid && triggers==1);
  nowMs=60;
  auto missing=sonar.read(nowMs);
  assert(!missing.valid && missing.mm==0 && triggers==2);
  nowMs=120; echo=25000;
  assert(!sonar.read(nowMs).valid);
  nowMs=180; echo=6000;
  auto range=sonar.read(nowMs);
  assert(range.valid && range.mm==1020 && range.timestamp==nowMs);
}
