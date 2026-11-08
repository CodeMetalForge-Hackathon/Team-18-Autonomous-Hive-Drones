#pragma once
#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <math.h>

// MPU-9250/AK8963 register interface; BMP280 compensation uses Adafruit's driver.
// Values remain in sensor axes. No chassis orientation or motion model is assumed.
class Imu {
 public:
  explicit Imu(TwoWire& bus) : wire(bus), barometer(&bus) {}
  bool present = false, barometerPresent = false, magnetometerPresent = false;
  uint8_t address = 0, chipId = 0, barometerAddress = 0;

  void begin() {
    for (uint8_t candidate : {uint8_t(0x68), uint8_t(0x69)}) {
      uint8_t id;
      if (read(candidate, 0x75, &id, 1) && (id == 0x71 || id == 0x73)) {
        address = candidate; chipId = id; break;
      }
    }
    if (address) {
      present = write(address, 0x6b, 0x01); // Wake; PLL clock.
      delay(10);
      present = write(address, 0x1a, 0x03) && present;
      present = write(address, 0x19, 9) && present; // 100 Hz.
      present = write(address, 0x1b, 0x18) && present; // +/-2000 deg/s.
      present = write(address, 0x1c, 0) && present; // +/-2 g.
      present = write(address, 0x1d, 3) && present;
      present = write(address, 0x37, 2) && present; // Expose AK8963 on I2C.
      uint8_t id;
      if (present && read(0x0c, 0, &id, 1) && id == 0x48) {
        bool ok = write(0x0c, 0x0a, 0); delay(1);
        ok = write(0x0c, 0x0a, 0x0f) && ok; delay(1);
        uint8_t adjustment[3];
        ok = read(0x0c, 0x10, adjustment, 3) && ok;
        if (ok) for (int i=0; i<3; ++i)
          magScale[i] = ((float(adjustment[i])-128)/256+1)*4912/32760;
        ok = write(0x0c, 0x0a, 0) && ok; delay(1);
        magnetometerPresent = write(0x0c, 0x0a, 0x16) && ok;
      }
    }
    for (uint8_t candidate : {uint8_t(0x76), uint8_t(0x77)}) {
      uint8_t id;
      if (read(candidate, 0xd0, &id, 1) && id == 0x58 && barometer.begin(candidate)) {
        barometerAddress = candidate; barometerPresent = true;
        barometer.setSampling(Adafruit_BMP280::MODE_NORMAL,
          Adafruit_BMP280::SAMPLING_X1, Adafruit_BMP280::SAMPLING_X1,
          Adafruit_BMP280::FILTER_OFF, Adafruit_BMP280::STANDBY_MS_1);
        break;
      }
    }
  }

  String sample() {
    uint8_t data[14];
    bool valid = present && read(address, 0x3b, data, sizeof(data));
    String result = String("{\"present\":") + (present ? "true" : "false")
      + ",\"valid\":" + (valid ? "true" : "false")
      + ",\"timestamp_ms\":" + millis()
      + ",\"chip_id\":" + chipId + ",\"address\":" + address;
    result += ",\"gyro_range_dps\":2000,\"accel_range_g\":2";
    result += ",\"acceleration_g\":";
    result += valid ? vector(data, 16384.0f) : "null";
    result += ",\"angular_velocity_dps\":";
    result += valid ? vector(data+8, 16.4f) : "null";
    bool accelClipped = false, gyroClipped = false;
    if (valid) for (int i=0; i<3; ++i) {
      accelClipped |= abs(int(int16_t(uint16_t(data[2*i])<<8 | data[2*i+1]))) >= 32760;
      gyroClipped |= abs(int(int16_t(uint16_t(data[8+2*i])<<8 | data[9+2*i]))) >= 32760;
    }
    result += String(",\"accel_saturated\":") + (accelClipped ? "true" : "false");
    result += String(",\"gyro_saturated\":") + (gyroClipped ? "true" : "false");
    uint8_t ready=0, mag[7];
    bool magValid = magnetometerPresent && read(0x0c, 0x02, &ready, 1)
      && (ready&1) && read(0x0c, 0x03, mag, 7) && !(mag[6]&8);
    result += String(",\"magnetometer_present\":") + (magnetometerPresent ? "true" : "false");
    result += String(",\"magnetometer_valid\":") + (magValid ? "true" : "false");
    result += ",\"magnetic_field_uT\":";
    if (magValid) {
      result += '[';
      for (int i=0; i<3; ++i) {
        if (i) result += ',';
        result += String(int16_t(uint16_t(mag[2*i]) | uint16_t(mag[2*i+1])<<8)*magScale[i], 4);
      }
      result += ']';
    } else result += "null";
    float pressure = barometerPresent ? barometer.readPressure() : NAN;
    float temperature = barometerPresent ? barometer.readTemperature() : NAN;
    bool pressureValid = isfinite(pressure) && pressure>0 && isfinite(temperature);
    result += String(",\"barometer_present\":") + (barometerPresent ? "true" : "false");
    result += String(",\"barometer_valid\":") + (pressureValid ? "true" : "false");
    result += ",\"pressure_pa\":" + (pressureValid ? String(pressure, 2) : String("null"));
    result += ",\"temperature_c\":" + (pressureValid ? String(temperature, 2) : String("null"));
    return result + '}';
  }
 private:
  TwoWire& wire;
  Adafruit_BMP280 barometer;
  float magScale[3] = {0,0,0};
  bool read(uint8_t device, uint8_t reg, uint8_t* data, uint8_t size) {
    wire.beginTransmission(device); wire.write(reg);
    if (wire.endTransmission(false) || wire.requestFrom(device, size)!=size) return false;
    for (int i=0; i<size; ++i) data[i]=wire.read();
    return true;
  }
  bool write(uint8_t device, uint8_t reg, uint8_t value) {
    wire.beginTransmission(device); wire.write(reg); wire.write(value);
    return wire.endTransmission()==0;
  }
  static String vector(const uint8_t* data, float divisor) {
    String result = "[";
    for (int i=0; i<3; ++i) {
      if (i) result += ',';
      result += String(int16_t(uint16_t(data[2*i])<<8 | data[2*i+1])/divisor, 5);
    }
    return result + ']';
  }
};
