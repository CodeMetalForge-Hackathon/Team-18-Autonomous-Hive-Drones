#include <assert.h>
#include <stdio.h>
#include "../firmware/roverc-test/Navigator.h"

int main() {
  Navigator n;
  assert(!n.start(1000, {false, 1000, 1000}));
  assert(n.update(1000, {true, 1000, 1000}) == 'S'); // fault needs restart
  assert(!n.start(1000, {true, 1000, 799})); // stale sensor
  assert(!n.start(1000, {true, 0, 1000})); // no echo is not clear space
  assert(n.start(1000, {true, 900, 1000}));
  assert(n.update(1100, {true, 900, 1100}) == 'S');
  assert(n.update(1200, {true, 900, 1200}) == 'F');
  assert(n.update(1250, {true, 250, 1250}) == 'S'); // obstacle immediately stops
  assert(n.update(1450, {true, 250, 1450}) == 'E');
  assert(n.update(1570, {true, 250, 1570}) == 'S'); // rotation pulse expires
  n.update(1600, {true, 800, 1600});
  n.update(1640, {true, 800, 1600}); // same echo must not count twice
  assert(n.state == Navigator::Turn);
  assert(n.update(1650, {true, 800, 1650}) == 'S');
  assert(n.update(1850, {true, 800, 1850}) == 'F');
  assert(n.update(2100, {true, 800, 1850}) == 'S');
  assert(n.state == Navigator::SensorFault);
  assert(n.start(3000, {true, 250, 3000}));
  n.update(3200, {true, 250, 3200});
  assert(n.update(6200, {true, 250, 6200}) == 'S');
  assert(n.state == Navigator::Blocked);
  n.stop();
  assert(n.update(6250, {true, 900, 6250}) == 'S');
  // Time arithmetic also works when the millisecond counter wraps.
  assert(n.start(0xfffffff0u, {true, 900, 0xfffffff0u}));
  assert(n.update(184, {true, 900, 184}) == 'F');
  puts("PASS: obstacle stop, clearance hysteresis, sensor freshness, pulse limit, stuck timeout, counter wrap.");
}
