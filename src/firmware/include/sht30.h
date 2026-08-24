#pragma once
// SHT30/SHT31 纯函数驱动层：无硬件依赖，host 单测可直接覆盖。
// 协议：单次测量高重复性命令 0x2C06，回读 6 字节 = [Tmsb,Tlsb,CRC,RHmsb,RHlsb,CRC]
#include <cstdint>
#include <cstddef>

namespace sht30 {

static constexpr uint8_t DEFAULT_ADDR = 0x44;

// CRC-8: poly 0x31, init 0xFF, MSB-first, 无最终异或（SHT3x 数据手册标准）
inline uint8_t crc8(const uint8_t* data, size_t len) {
  uint8_t crc = 0xFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int b = 0; b < 8; ++b)
      crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x31)
                         : static_cast<uint8_t>(crc << 1);
  }
  return crc;
}

struct Sample {
  float temp_c = 0.f;
  float rh_pct = 0.f;
  bool ok = false;
};

// 校验双 CRC 并换算物理量；任一 CRC 错则返回 false。
inline bool parse(const uint8_t raw[6], Sample* out) {
  if (!raw || !out) return false;
  if (crc8(&raw[0], 2) != raw[2]) return false;
  if (crc8(&raw[3], 2) != raw[5]) return false;
  const uint16_t rt = static_cast<uint16_t>((raw[0] << 8) | raw[1]);
  const uint16_t rh = static_cast<uint16_t>((raw[3] << 8) | raw[4]);
  out->temp_c = -45.0f + 175.0f * (static_cast<float>(rt) / 65535.0f);
  float h = 100.0f * (static_cast<float>(rh) / 65535.0f);
  if (h < 0.f) h = 0.f;
  if (h > 100.f) h = 100.f;
  out->rh_pct = h;
  out->ok = true;
  return true;
}

} // namespace sht30
