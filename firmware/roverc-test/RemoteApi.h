#pragma once

bool apiKey() {
  if (web.header("X-Rover-Key") != wifiPassword) {
    replyError(403, "Invalid access key"); return false;
  }
  return true;
}
bool apiOwner() {
  if (!apiKey()) return false;
  serviceWifiSafety();
  if (!remoteToken.length() || web.header("X-Rover-Token") != remoteToken || physicalStop) {
    replyError(409, "Control lease required"); return false;
  }
  remoteSeen = millis();
  return true;
}
bool apiInteger(const char* name, int low, int high, int& result) {
  String value = web.arg(name);
  if (!value.length() || value.length() > 7) return false;
  unsigned start = value[0] == '-' ? 1 : 0;
  if (start == value.length()) return false;
  for (unsigned i=start; i<value.length(); ++i)
    if (value[i] < '0' || value[i] > '9') return false;
  long number = strtol(value.c_str(), nullptr, 10);
  if (number < low || number > high) return false;
  result = number; return true;
}
void apiStatus() {
  connected = probe();
  char body[440];
  snprintf(body, sizeof(body),
    "{\"protocol\":3,\"connected\":%d,\"moving\":%d,\"armed\":%d,"
    "\"stop_ack\":%d,\"stop_pending\":%d,\"error_count\":%lu,"
    "\"last_error\":%u,\"last_wheel\":%u,\"uptime_ms\":%lu}",
    connected, moving, armed, stopAcknowledged, stopPending,
    (unsigned long)motorErrorCount, lastMotorError, lastMotorErrorWheel, (unsigned long)millis());
  web.send(200, "application/json", body);
}
void apiStop() {
  navigator.stop(); stopMotors(); armed=false; M5.Speaker.stop();
  if (!stopAcknowledged || stopPending) { replyError(503,"Stop not acknowledged"); return; }
  apiStatus();
}
void registerRemoteApi() {
  web.on("/api/robot/status", HTTP_GET, []{ if(apiKey()) apiStatus(); });
  web.on("/api/robot/capabilities", HTTP_GET, []{
    if(!apiKey())return;
    web.send(200,"application/json","{\"version\":3,\"servo_channels\":2,\"buzzer\":1,\"imu\":1,\"wheel_limit\":40,\"pulse_limit\":60,\"pulse_max_ms\":150}");
  });
  web.on("/api/robot/claim", HTTP_POST, []{
    if(!apiKey())return;
    serviceWifiSafety();
    if(remoteToken.length() || moving || armed) { replyError(409,"Controller already active"); return; }
    if(digitalRead(39)==LOW) { replyError(409,"Release stop button"); return; }
    char token[33];
    snprintf(token,sizeof(token),"%08lx%08lx%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random());
    physicalStop=false; remoteToken=token; remoteSequence=0; remoteSeen=millis();
    remoteRaw=true;
    remoteViaStation = web.client().localIP() != WiFi.softAPIP();
    web.send(200,"application/json",String("{\"token\":\"")+remoteToken+"\"}");
  });
  web.on("/api/robot/release", HTTP_POST, []{
    if(!apiOwner())return;
    apiStop(); revokeRemote();
  });
  web.on("/api/robot/stop", HTTP_POST, []{ if(apiOwner() && readSequence()) apiStop(); });
  web.on("/api/robot/wheels", HTTP_POST, []{
    if(!apiOwner() || !readSequence())return;
    int values[4], duration=0, pulse=0;
    bool valid=apiInteger("pulse",0,1,pulse) && apiInteger("duration_ms",20,pulse ? 150 : 300,duration);
    for(int i=0; i<4; ++i) {
      char key[3];snprintf(key,sizeof(key),"w%d",i);
      valid=apiInteger(key,pulse ? -60 : -40,pulse ? 60 : 40,values[i]) && valid;
    }
    if(!valid) { navigator.stop();stopMotors();armed=false;replyError(400,"Invalid wheel command");return; }
    if(pulse && moving) { replyError(409,"Already moving");return; }
    int8_t speeds[4]; for(int i=0;i<4;++i)speeds[i]=values[i];
    navigator.stop(); armed=true;
    if(!driveWheels(speeds,pulse ? 60 : 40,duration)) {
      stopMotors();armed=false;replyError(503,"Motor command failed");return;
    }
    web.send(200,"application/json","{\"accepted\":true}");
  });
  web.on("/api/robot/imu", HTTP_GET, []{
    if (!apiKey()) return;
    xSemaphoreTake(motorMutex, portMAX_DELAY);
    String reading = imu.sample();
    xSemaphoreGive(motorMutex);
    web.send(200, "application/json", reading);
  });
  web.on("/api/robot/sonar", HTTP_GET, []{
    if(!apiKey())return;
    rangeReading=sonar.read(millis());
    char body[220];
    snprintf(body,sizeof(body),"{\"configured\":%d,\"valid\":%d,\"range_mm\":%u,\"age_ms\":%lu,\"signal_pin\":%d,\"echo_us\":%lu}",
      Sonar::configured,Navigator::usable(millis(),rangeReading),rangeReading.mm,
      (unsigned long)(millis()-rangeReading.timestamp),Sonar::signalPin,sonar.echoMicroseconds());
    web.send(200,"application/json",body);
  });
  web.on("/api/robot/servos", HTTP_GET, []{
    if(!apiKey())return;
    uint8_t data[6];bool ok=true;
    xSemaphoreTake(motorMutex,portMAX_DELAY);
    for(int part=0;part<2;++part) {
      int count=part ? 4 : 2,offset=part ? 2 : 0;
      rover.beginTransmission(ADDRESS);rover.write(part ? 0x20 : 0x10);
      if(rover.endTransmission(false) || rover.requestFrom(ADDRESS,uint8_t(count))!=count) { ok=false;break; }
      for(int i=0;i<count;++i)data[offset+i]=rover.read();
    }
    xSemaphoreGive(motorMutex);
    if(!ok) {replyError(503,"Servo read failed");return;}
    char body[180];snprintf(body,sizeof(body),"{\"angle1\":%u,\"angle2\":%u,\"pulse1_us\":%u,\"pulse2_us\":%u,\"feedback\":\"target_registers\"}",
      data[0],data[1],(data[2]<<8)|data[3],(data[4]<<8)|data[5]);
    web.send(200,"application/json",body);
  });
  web.on("/api/robot/servo", HTTP_POST, []{
    if(!apiOwner() || !readSequence())return;
    int channel=0,value=0,pulse=0;
    if(!apiInteger("channel",1,2,channel) || !apiInteger("pulse",0,1,pulse) ||
       !apiInteger("value",pulse ? 500 : 0,pulse ? 2500 : 180,value)) {replyError(400,"Invalid servo command");return;}
    if(moving) {replyError(409,"Wheels must be stopped");return;}
    navigator.stop();
    if(!writeServo(channel,value,pulse)) {replyError(503,"Servo command failed");return;}
    web.send(200,"application/json","{\"accepted\":true,\"feedback\":\"target_registers\"}");
  });
  web.on("/api/robot/buzzer", HTTP_GET, []{
    if(!apiKey())return;
    char body[100];snprintf(body,sizeof(body),"{\"enabled\":%d,\"playing\":%d,\"volume\":%u,\"pin\":2}",
      M5.Speaker.isEnabled(),M5.Speaker.isPlaying(),M5.Speaker.getVolume());
    web.send(200,"application/json",body);
  });
  web.on("/api/robot/tone", HTTP_POST, []{
    if(!apiOwner() || !readSequence())return;
    int frequency,duration,volume;
    if(!apiInteger("frequency",20,20000,frequency) || !apiInteger("duration_ms",1,5000,duration) || !apiInteger("volume",0,255,volume)) {replyError(400,"Invalid tone");return;}
    M5.Speaker.setVolume(volume);
    if(!M5.Speaker.tone(frequency,duration)) {replyError(503,"Buzzer failed");return;}
    web.send(200,"application/json","{\"accepted\":true}");
  });
  web.on("/api/robot/silence", HTTP_POST, []{
    if(!apiOwner() || !readSequence())return;
    M5.Speaker.stop();web.send(200,"application/json","{\"accepted\":true}");
  });
}
