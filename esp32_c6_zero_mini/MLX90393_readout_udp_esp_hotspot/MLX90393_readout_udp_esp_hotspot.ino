/*
  eFlesh Board Code
  By: Venkatesh P
  Date: August 1, 2025
  License: This code is public domain but you buy me a beer if you use this and we meet someday (Beerware license).

  Credits: Adapted from (ReSkin (https://reskin.dev) and AnySkin (https://any-skin.github.io) repos) - maintained by Raunaq Bhirangi, Tess Hellebrekers
  Library: Heavily based on original MLX90393 library from Theodore Yapo (https://github.com/tedyapo/arduino-MLX90393)
  Library: https://github.com/tesshellebrekers/arduino-MLX90393  (required)
*/

#include <Wire.h>
#include "MLX90393.h"
#include <WiFi.h>
#include <WiFiUdp.h>

#define SDA_PIN 0   // choose your GPIO
#define SCL_PIN 1   // choose your GPIO

// ---------------- WIFI ----------------
WiFiUDP udp;
const char* apSsid = "DynaSense-ESP32";
const char* apPass = "12345678";
IPAddress apIP(192, 168, 4, 1);
IPAddress apGateway(192, 168, 4, 1);
IPAddress apSubnet(255, 255, 255, 0);
IPAddress remoteIP;
int remotePort = 4210;
bool clientFound = false;
char incoming[64];


// MLX90393 objects and data buffers
static const uint8_t NUM_SENSORS = 8;
MLX90393 mlx[NUM_SENSORS];

// Forward decls
void scanI2C(uint8_t* found, uint8_t& count);
uint8_t foundCount = 0;

// ---------------- UDP SEND ----------------
inline void sendPacket(float *data) {
  udp.beginPacket(remoteIP, remotePort);
  udp.write((uint8_t*)data, 24 * sizeof(float));
  udp.endPacket();
}

void setup() {
  #ifdef RGB_BUILTIN
    neopixelWrite(RGB_BUILTIN,0,RGB_BRIGHTNESS,0); // Red
  #endif
  Serial.begin(921600);
  Serial.println("Starting setup");
  int serial_connect_attempts = 5;
  while (!Serial && serial_connect_attempts > 0) {
    delay(5);
    serial_connect_attempts--;
  }

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);
  delay(10);

  uint8_t found[16] = {0};

  scanI2C(found, foundCount);

  Serial.println(F("I2C scan complete."));
  Serial.print(F("Found MLX candidates: "));
  for (uint8_t i = 0; i < foundCount; ++i) {
    Serial.print("0x"); Serial.print(found[i], HEX); Serial.print(" ");
    byte status = mlx[i].begin(found[i], 7, Wire);
    Serial.print(F("Init MLX[")); Serial.print(i); Serial.print(F("] @0x"));
    Serial.print(found[i], HEX);
    Serial.print(F(" status=")); Serial.println(status, HEX);

    // Configs
    mlx[i].setGainSel(0x1);
    mlx[i].setResolution(0x2, 0x2, 0x2);
    mlx[i].setDigitalFiltering(0x4);

    // Start burst mode (Temp + X + Y + Z) = 0xF
    byte statusTest = mlx[i].startBurst(0xF);
    Serial.print(F(" statusTest="));Serial.println(statusTest, HEX);
  }

  Serial.print("Found ");Serial.print(foundCount);Serial.print("/");Serial.print(NUM_SENSORS);Serial.println(" Sensors");

  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.softAPConfig(apIP, apGateway, apSubnet);

  if (!WiFi.softAP(apSsid, apPass)) {
    Serial.println("Failed to start SoftAP");
  }

  Serial.print("AP SSID: ");
  Serial.println(apSsid);
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());

  #ifdef RGB_BUILTIN
    neopixelWrite(RGB_BUILTIN,0,0,RGB_BRIGHTNESS); // Blue
  #endif

  udp.begin(4210);
  while (!clientFound) {
    int len = udp.parsePacket();
    if (len) {
      int n = udp.read(incoming, sizeof(incoming) - 1);
      incoming[n] = 0;

      if (strcmp(incoming, "DISCOVER") == 0) {
        remoteIP = udp.remoteIP();
        clientFound = true;
      }
    }
  }
  #ifdef RGB_BUILTIN
    neopixelWrite(RGB_BUILTIN,RGB_BRIGHTNESS,0,0); // Green
  #endif

}

void loop() {
  MLX90393::txyzRaw raw_txyz[NUM_SENSORS];
  MLX90393::txyz txyz[NUM_SENSORS];
  float packet[24] = {0.0f};
  for (int i = 0; i < NUM_SENSORS; i++){
    if (i < foundCount){
      byte statusCheck = mlx[i].readMeasurement(0xF, raw_txyz[i]);
      txyz[i] = mlx[i].convertRaw(raw_txyz[i]);
      packet[0+i*3] = txyz[i].x;
      packet[1+i*3] = txyz[i].y;
      packet[2+i*3] = txyz[i].z;
    } else {
      packet[0+i*3] = 0;
      packet[1+i*3] = 0;
      packet[2+i*3] = 0;
    }
  }
  sendPacket(packet);
}

// Scan all I2C addresses to find MLX90393 sensors
void scanI2C(uint8_t* found, uint8_t& count) {
  count = 0;
  for (uint8_t addr = 0x08; addr <= 0x77; addr++) {
    Wire.beginTransmission(addr);
    uint8_t err = Wire.endTransmission();
    if (err == 0) {
      found[count++] = addr;
      if (count >= 16) break;
    }
  }
}