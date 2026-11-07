#include <M5Unified.h>
#include <Wire.h>
#include "Sonar.h"

// M5Unified reserves bus 1 for the internal AXP192/RTC.
TwoWire rover(0);
constexpr uint8_t ADDRESS = 0x38;
volatile bool moving = false;
volatile uint32_t stopAt = 0;
volatile bool watchdogExpired = false;
volatile uint32_t watchdogStopAt = 0;
volatile bool physicalStop = false;
volatile uint8_t lastMotorError = 0, lastMotorErrorWheel = 0;
volatile uint32_t motorErrorCount = 0;
volatile bool stopAcknowledged = false;
volatile bool stopPending = true;
SemaphoreHandle_t motorMutex;
int nextWheel = 0;
bool connected = false;
bool armed = false;
bool markerMode = false;
uint32_t lastCheck = 0;
Navigator navigator;
Sonar sonar;
RangeReading rangeReading = {false, 0, 0};
uint32_t lastSense = 0;
int nextMotion = 0;
const char* motionNames[] = {"Forward", "Reverse", "Strafe L", "Strafe R", "Rotate L", "Rotate R"};
const char motions[] = {'F', 'B', 'L', 'R', 'Q', 'E'};

bool setMotor(uint8_t wheel, int8_t speed) {
  rover.beginTransmission(ADDRESS);
  rover.write(wheel);
  rover.write((uint8_t)speed);
  uint8_t result = rover.endTransmission();
  if (result) { lastMotorError=result; lastMotorErrorWheel=wheel; ++motorErrorCount; }
  return result == 0;
}
void stopLocked() {
  bool ok = true;
  for (int i = 0; i < 4; ++i) if (!setMotor(i, 0)) ok = false;
  moving = false;
  stopAcknowledged = ok;
  stopPending = !ok;
}
void stopMotors(bool force = false) {
  xSemaphoreTake(motorMutex, portMAX_DELAY);
  if (force || moving || !stopAcknowledged) stopLocked();
  xSemaphoreGive(motorMutex);
}
bool probe() {
  xSemaphoreTake(motorMutex, portMAX_DELAY);
  rover.beginTransmission(ADDRESS);
  bool found = rover.endTransmission() == 0;
  xSemaphoreGive(motorMutex);
  return found;
}
void motorWatchdog(void*) {
  for (;;) {
    if (digitalRead(39) == LOW) physicalStop = true;
    xSemaphoreTake(motorMutex, portMAX_DELAY);
    bool expired = moving && (physicalStop || (int32_t)(millis() - stopAt) >= 0);
    if (expired || stopPending) {
      stopLocked();
      if (expired) { watchdogStopAt=millis(); watchdogExpired=true; }
    }
    xSemaphoreGive(motorMutex);
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}
void wifiScreen();
void markerScreen() {
  M5.Display.fillScreen(TFT_BLACK);
  int width = M5.Display.width(), height = M5.Display.height();
  M5.Display.fillRect(0, 0, width*3/8, height, TFT_CYAN);
  M5.Display.fillRect(width*5/8, 0, width-width*5/8, height, TFT_MAGENTA);
}
void screen() {
  if (markerMode) { markerScreen(); return; }
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setCursor(4, 4);
  M5.Display.setTextColor(TFT_WHITE);
  M5.Display.setTextSize(2);
  M5.Display.println("RoverC Pro");
  M5.Display.println("Wi-Fi control");
  M5.Display.setTextColor(connected ? TFT_GREEN : TFT_YELLOW);
  M5.Display.println(connected ? "Rover: FOUND" : "Rover: OFF?");
  M5.Display.setTextColor(TFT_WHITE);
  M5.Display.setTextSize(1);
  wifiScreen();
  M5.Display.printf("A:200ms B:STOP Next:%c", motions[nextMotion]);
}
void report() {
  Serial.printf("ROVER_STATUS connected=%d moving=%d armed=%d next_wheel=%d address=0x38 sda=0 scl=26\n", connected, moving, armed, nextWheel + 1);
  Serial.printf("AGENT_STATUS sonar_configured=%d range_valid=%d range_mm=%u auto_state=%d next_motion=%c\n", Sonar::configured, Navigator::usable(millis(), rangeReading), rangeReading.mm, navigator.state, motions[nextMotion]);
  Serial.printf("MOTOR_DIAG error_count=%lu last_error=%u last_wheel=%u stop_ack=%d stop_pending=%d\n", (unsigned long)motorErrorCount, lastMotorError, lastMotorErrorWheel, stopAcknowledged, stopPending);
}
bool driveWheels(const int8_t speeds[4], int limit = 40, uint32_t durationMs = 300) {
  if (physicalStop || digitalRead(39) == LOW) { stopMotors(); return false; }
  for (int i=0; i<4; ++i) if (speeds[i] < -limit || speeds[i] > limit) { stopMotors(); return false; }
  xSemaphoreTake(motorMutex, portMAX_DELAY);
  if (stopPending) { xSemaphoreGive(motorMutex); Serial.println("STOP_UNCONFIRMED"); return false; }
  stopAcknowledged = false;
  bool ok = true;
  for (int i=0; i<4; ++i) {
    if (!setMotor(i, speeds[i])) { ok = false; break; }
  }
  if (ok) { stopAt=millis()+durationMs; moving=true; }
  else { stopLocked(); }
  xSemaphoreGive(motorMutex);
  if (!ok) { navigator.stop(); armed=false; connected=false; Serial.println("ROVER_NOT_FOUND"); return false; }
  return true;
}
bool drive(char direction, int speed) {
  int8_t signs[4];
  switch (direction) {
    case 'F': signs[0]=1; signs[1]=1; signs[2]=1; signs[3]=1; break;
    case 'B': signs[0]=-1; signs[1]=-1; signs[2]=-1; signs[3]=-1; break;
    case 'L': signs[0]=-1; signs[1]=1; signs[2]=1; signs[3]=-1; break;
    case 'R': signs[0]=1; signs[1]=-1; signs[2]=-1; signs[3]=1; break;
    case 'Q': signs[0]=1; signs[1]=-1; signs[2]=1; signs[3]=-1; break;
    case 'E': signs[0]=-1; signs[1]=1; signs[2]=-1; signs[3]=1; break;
    default: stopMotors(); return false;
  }
  for (int i=0; i<4; ++i) signs[i] *= speed;
  return driveWheels(signs);
}
void startAuto() {
  stopMotors(); armed=false;
  connected=probe();
  rangeReading=sonar.read(millis());
  if (!connected || !stopAcknowledged) { navigator.stop(); Serial.println("ROVER_NOT_FOUND"); return; }
  if (!navigator.start(millis(), rangeReading)) { Serial.println("SONAR_UNAVAILABLE"); return; }
  Serial.println("AUTO_STARTED");
}
void command(const char* cmd) {
  if (M5.BtnB.isPressed()) { navigator.stop(); stopMotors(); armed=false; Serial.println("DISARMED"); return; }
  if (!strcmp(cmd, "STOP") || !strcmp(cmd, "DISARM")) {
    navigator.stop();
    stopMotors();
    if (!strcmp(cmd, "DISARM")) armed = false;
    Serial.println("STOPPED");
  } else if (!strcmp(cmd, "STATUS")) {
    connected = probe(); report();
  } else if (!strcmp(cmd, "MARKER") || !strcmp(cmd, "UI")) {
    navigator.stop(); stopMotors(); armed=false;
    markerMode = !strcmp(cmd, "MARKER");
    screen();
    Serial.println(markerMode ? "MARKER_READY" : "UI_READY");
  } else if (!strcmp(cmd, "ARM")) {
    physicalStop=false; watchdogExpired=false;
    navigator.stop();
    stopMotors(true); connected = probe(); armed = connected && stopAcknowledged;
    Serial.println(armed ? "ARMED" : "ROVER_NOT_FOUND");
  } else if (!strcmp(cmd, "AUTO")) {
    startAuto();
  } else if (!strncmp(cmd, "PULSE ", 6)) {
    navigator.stop();
    int duration, speeds[4]; char extra;
    bool valid = sscanf(cmd, "PULSE %d %d %d %d %d %c", &duration, &speeds[0], &speeds[1], &speeds[2], &speeds[3], &extra) == 5;
    valid = valid && duration >= 20 && duration <= 150;
    for (int i=0; valid && i<4; ++i) valid = speeds[i] >= -60 && speeds[i] <= 60;
    if (!valid) { stopMotors(); Serial.println("INVALID_COMMAND"); return; }
    if (!armed) { stopMotors(); Serial.println("DISARMED"); return; }
    if (moving) { stopMotors(); armed=false; Serial.println("INVALID_BUSY"); return; }
    int8_t wheelSpeeds[4];
    for (int i=0; i<4; ++i) wheelSpeeds[i] = speeds[i];
    Serial.println(driveWheels(wheelSpeeds, 60, duration) ? "DRIVING" : "MOTOR_ERROR");
  } else if (!strncmp(cmd, "WHEELS ", 7)) {
    navigator.stop();
    int speeds[4]; char extra;
    bool valid = sscanf(cmd, "WHEELS %d %d %d %d %c", &speeds[0], &speeds[1], &speeds[2], &speeds[3], &extra) == 4;
    for (int i=0; valid && i<4; ++i) valid = speeds[i] >= -40 && speeds[i] <= 40;
    if (!valid) { stopMotors(); Serial.println("INVALID_COMMAND"); return; }
    if (!armed) { stopMotors(); Serial.println("DISARMED"); return; }
    int8_t wheelSpeeds[4];
    for (int i=0; i<4; ++i) wheelSpeeds[i] = speeds[i];
    Serial.println(driveWheels(wheelSpeeds) ? "DRIVING" : "MOTOR_ERROR");
  } else {
    navigator.stop();
    char direction, extra; int speed;
    if (sscanf(cmd, "DRIVE %c %d %c", &direction, &speed, &extra) != 2 || speed < 0 || speed > 40) {
      stopMotors(); Serial.println("INVALID_COMMAND"); return;
    }
    if (!armed) { stopMotors(); Serial.println("DISARMED"); return; }
    Serial.println(drive(direction, speed) ? "DRIVING" : "INVALID_DIRECTION");
  }
}
#include "WifiControl.h"
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("INIT_DISPLAY");
  auto cfg = M5.config();
  cfg.serial_baudrate = 115200;
  cfg.external_display_value = 0;
  cfg.internal_mic = false;
  cfg.internal_imu = false;
  cfg.internal_spk = false;
  cfg.fallback_board = m5::board_t::board_M5StickCPlus;
  M5.begin(cfg);
  Serial.println("DISPLAY_READY");
  Serial.begin(115200);
  M5.Display.setRotation(1);
  pinMode(25, INPUT);
  pinMode(36, INPUT);
  rover.begin(0, 26, 100000);
  rover.setTimeOut(20);
  motorMutex = xSemaphoreCreateMutex();
  if (!motorMutex) { Serial.println("MOTOR_MUTEX_FAILED"); while (true) delay(100); }
  sonar.begin();
  stopMotors();
  connected = probe();
  xTaskCreatePinnedToCore(motorWatchdog, "motor-stop", 3072, nullptr, 3, nullptr, 1);
  beginWifi();
  screen();
  Serial.println("ROVER_TEST_READY motors=stopped; A=next whole-body motion, speed20/200ms; hold A=sonar auto; B=stop");
  report();
}
void loop() {
  M5.update();
  serviceWifiSafety();
  if (physicalStop) { navigator.stop(); stopMotors(); armed=false; }
  if (M5.BtnB.wasPressed()) { navigator.stop(); stopMotors(); armed=false; Serial.println("DISARMED"); }
  if (M5.BtnA.wasHold() && !M5.BtnB.isPressed() && !armed) startAuto();
  if (M5.BtnA.wasClicked() && !M5.BtnB.isPressed() && !moving && !armed && !navigator.active()) {
    physicalStop=false; watchdogExpired=false;
    stopMotors();
    connected = probe();
    if (connected && drive(motions[nextMotion], 20)) {
      stopAt = millis() + 200;
      Serial.printf("TEST_MOTION %c speed=20 duration_ms=200\n", motions[nextMotion]);
      nextMotion = (nextMotion + 1) % 6;
    } else { stopMotors(); Serial.println("ROVER_NOT_FOUND"); }
    screen();
  }
  for (uint8_t bytesRead = 0; Serial.available() && bytesRead < 64; ++bytesRead) {
    static char cmd[32]; static uint8_t count = 0; static bool overflow = false;
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      cmd[count] = 0;
      if (overflow) { navigator.stop(); stopMotors(); armed=false; Serial.println("INVALID_COMMAND"); }
      else if (!strcmp(cmd, "WIFI")) reportWifi();
      else if (count) { if (strcmp(cmd, "STATUS")) revokeRemote(); command(cmd); }
      count = 0; overflow = false;
    } else if (count < sizeof(cmd)-1) cmd[count++] = c;
    else overflow = true;
  }
  web.handleClient();
  if (millis() - lastSense >= 50) {
    lastSense = millis();
    rangeReading = sonar.read(lastSense);
    if (navigator.active() && !M5.BtnB.isPressed()) {
      char action = navigator.update(millis(), rangeReading);
      if (action == 'S') stopMotors();
      else drive(action, 20);
      if (!navigator.active()) { stopMotors(); armed=false; Serial.println("AUTO_STOPPED"); }
    }
  }
  if (!moving && millis() - lastCheck >= 2000) {
    lastCheck = millis();
    bool found = probe();
    if (found != connected) { connected = found; stopMotors(); screen(); report(); }
  }
  delay(2);
}
