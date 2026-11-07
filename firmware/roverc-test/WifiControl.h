#pragma once
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include "ControlPage.h"

WebServer web(80);
String wifiName, wifiPassword, remoteToken;
uint32_t remoteSequence = 0, remoteSeen = 0;

void revokeRemote() { remoteToken=""; remoteSequence=0; }
void serviceWifiSafety() {
  if (watchdogExpired) {
    watchdogExpired=false; navigator.stop(); stopMotors();
    if (remoteToken.length()) { armed=false; revokeRemote(); }
    Serial.println("TIMED_STOP");
  }
  if (physicalStop || (remoteToken.length() &&
      (millis()-remoteSeen>1500 || WiFi.softAPgetStationNum()==0))) {
    if (remoteToken.length()) { navigator.stop(); stopMotors(); armed=false; revokeRemote(); }
  }
}
void wifiScreen() {
  M5.Display.println(wifiName);
  M5.Display.println("Pass: " + wifiPassword);
  M5.Display.println("http://192.168.4.1");
}
void reportWifi() {
  Serial.printf("WIFI_READY ssid=%s password=%s ip=%s clients=%d\n", wifiName.c_str(), wifiPassword.c_str(), WiFi.softAPIP().toString().c_str(), WiFi.softAPgetStationNum());
}
void replyError(int code, const char* message) {
  web.send(code,"application/json",String("{\"error\":\"")+message+"\"}");
}
bool isControlRequest() {
  if (web.header("X-Rover-Control")!="1") { replyError(403,"Use the rover control page"); return false; }
  String origin=web.header("Origin");
  if (origin.length() && origin!="http://192.168.4.1") { replyError(403,"Invalid origin"); return false; }
  return true;
}
bool ownsControl() {
  serviceWifiSafety();
  if (!remoteToken.length() || web.header("X-Rover-Token")!=remoteToken || !armed || physicalStop) {
    replyError(409,"Disarmed or another controller owns the rover"); return false;
  }
  remoteSeen=millis(); return true;
}
bool readSequence() {
  String input=web.arg("seq");
  if (!input.length() || input.length()>9) { replyError(400,"Invalid sequence"); return false; }
  for(unsigned i=0;i<input.length();i++) if(input[i]<'0'||input[i]>'9') { replyError(400,"Invalid sequence"); return false; }
  uint32_t sequence=strtoul(input.c_str(),nullptr,10);
  if(sequence<=remoteSequence) { replyError(409,"Expired command"); return false; }
  remoteSequence=sequence; return true;
}
void beginWifi() {
  Preferences settings;
  if (!settings.begin("rover-wifi",false)) { Serial.println("WIFI_STORAGE_FAILED"); return; }
  wifiPassword=settings.getString("password","");
  if(wifiPassword.length()<12) {
    char password[17]; snprintf(password,sizeof(password),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
    wifiPassword=password; settings.putString("password",wifiPassword);
  }
  settings.end();
  char suffix[7]; snprintf(suffix,sizeof(suffix),"%06lx",(unsigned long)((ESP.getEfuseMac()>>24)&0xffffff));
  wifiName=String("RoverC18-")+suffix;
  WiFi.mode(WIFI_AP);
  if(!WiFi.softAP(wifiName.c_str(),wifiPassword.c_str(),6,false,2)) { Serial.println("WIFI_AP_FAILED"); return; }
  const char* headers[]={"X-Rover-Control","X-Rover-Token","Origin"};
  web.collectHeaders(headers,3);
  web.on("/",HTTP_GET,[]{web.sendHeader("Cache-Control","no-store");web.send_P(200,"text/html",CONTROL_PAGE);});
  web.on("/api/status",HTTP_GET,[]{
    serviceWifiSafety();
    bool owner=remoteToken.length() && web.header("X-Rover-Token")==remoteToken;
    if(owner)remoteSeen=millis();
    char body[260];snprintf(body,sizeof(body),"{\"connected\":%s,\"armed\":%s,\"moving\":%s,\"owner\":%s,\"sonar\":%s,\"uptime_ms\":%lu,\"drive_deadline_ms\":%lu,\"watchdog_stop_ms\":%lu}",connected?"true":"false",armed?"true":"false",moving?"true":"false",owner?"true":"false",Sonar::configured?"true":"false",(unsigned long)millis(),(unsigned long)stopAt,(unsigned long)watchdogStopAt);
    web.sendHeader("Cache-Control","no-store");web.send(200,"application/json",body);
  });
  web.on("/api/arm",HTTP_POST,[]{
    if(!isControlRequest())return;
    serviceWifiSafety();
    if(remoteToken.length()) { replyError(409,"Controller already active; press STOP first"); return; }
    if(M5.BtnB.isPressed() || digitalRead(39)==LOW) { replyError(409,"Release the B stop button");return; }
    command("ARM");
    if(!armed){replyError(409,"Rover not found");return;}
    char token[33];snprintf(token,sizeof(token),"%08lx%08lx%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random());
    remoteToken=token;remoteSequence=0;remoteSeen=millis();
    web.send(200,"application/json",String("{\"token\":\"")+remoteToken+"\"}");
  });
  web.on("/api/drive",HTTP_POST,[]{
    if(!isControlRequest()||!ownsControl()||!readSequence())return;
    String d=web.arg("d"),s=web.arg("s");
    bool valid=d.length()==1 && strchr("FBLRQE",d[0]) && s.length()>0 && s.length()<=2;
    for(unsigned i=0;i<s.length();i++)valid=valid && s[i]>='0' && s[i]<='9';
    int speed=s.toInt();
    if(!valid||speed>40){command("DISARM");revokeRemote();replyError(400,"Invalid drive command");return;}
    if(!drive(d[0],speed)){armed=false;revokeRemote();replyError(409,"Motor command failed");return;}
    web.send(200,"application/json","{\"ok\":true}");
  });
  web.on("/api/stop",HTTP_POST,[]{
    if(!isControlRequest()||!ownsControl()||!readSequence())return;
    stopMotors();web.send(200,"application/json","{\"ok\":true}");
  });
  web.on("/api/disarm",HTTP_POST,[]{
    if(!isControlRequest())return;
    command("DISARM");revokeRemote();web.send(200,"application/json","{\"ok\":true}");
  });
  web.onNotFound([]{web.send(404,"text/plain","Not found");});
  web.begin();reportWifi();
}
