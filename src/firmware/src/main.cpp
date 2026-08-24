#include <Arduino.h>
#include <Wire.h>
#include "sht30.h"

// M2 v0.1 温湿度记录仪固件：SHT30 单次采样 → JSON 行输出（UART/USB-CDC）
// 引脚约定与硬件设计一致（intent_v1）：SDA=GPIO4(IO4), SCL=GPIO5(IO5)
// 注：避开 GPIO8/9 strapping 脚；GPIO9 留给 BOOT 按键
static constexpr uint8_t SHT_ADDR = sht30::DEFAULT_ADDR;
static constexpr uint8_t PIN_SDA = 4;
static constexpr uint8_t PIN_SCL = 5;
static uint32_t g_seq = 0;

#ifdef SIM_STUB_SENSOR
// Wokwi 无 SHT31 零件：仿真构建用确定性合成样本（证据级 B：仅验证固件管线/JSON/时序）
static bool readSHT30(sht30::Sample* out) {
  out->temp_c = 25.00f + static_cast<float>(g_seq % 10) * 0.1f;
  out->rh_pct = 50.0f + static_cast<float>(g_seq % 5);
  out->ok = true;
  delay(20);
  return true;
}
#else
static bool readSHT30(sht30::Sample* out) {
  Wire.beginTransmission(SHT_ADDR);
  Wire.write(0x2C); // 单次测量、高重复性、时钟拉伸
  Wire.write(0x06);
  if (Wire.endTransmission() != 0) return false;
  delay(20); // 测量时间 max ~15ms
  if (Wire.requestFrom(static_cast<int>(SHT_ADDR), 6) != 6) return false;
  uint8_t raw[6];
  for (auto& b : raw) b = static_cast<uint8_t>(Wire.read());
  return sht30::parse(raw, out);
}
#endif

void setup() {
  Serial.begin(115200);
  Wire.begin(PIN_SDA, PIN_SCL);
  Serial.println("{\"boot\":\"sht30-logger\",\"ver\":1}");
}

void loop() {
  sht30::Sample s;
  if (readSHT30(&s)) {
    Serial.printf("{\"seq\":%lu,\"t_c\":%.2f,\"rh\":%.1f}\n",
                  static_cast<unsigned long>(++g_seq), s.temp_c, s.rh_pct);
  } else {
    Serial.printf("{\"seq\":%lu,\"err\":\"sht30_read\"}\n",
                  static_cast<unsigned long>(++g_seq));
  }
  delay(2000);
}
