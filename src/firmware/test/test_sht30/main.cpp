#include <unity.h>
#include "sht30.h"

void setUp() {}
void tearDown() {}

// SHT3x 数据手册标准 CRC 测试向量：0xBEEF -> 0x92
void test_crc_datasheet_vector(void) {
  const uint8_t d[2] = {0xBE, 0xEF};
  TEST_ASSERT_EQUAL_HEX8_MESSAGE(0x92, sht30::crc8(d, 2), "datasheet CRC vector");
}

void test_parse_good_frame(void) {
  uint8_t f[6] = {0x66, 0x66, 0x00, 0x80, 0x00, 0x00};
  f[2] = sht30::crc8(f, 2);
  f[5] = sht30::crc8(f + 3, 2);
  sht30::Sample s;
  TEST_ASSERT_TRUE(sht30::parse(f, &s));
  TEST_ASSERT_TRUE(s.ok);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, -45.0f + 175.0f * (0x6666 / 65535.0), s.temp_c);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 50.0f, s.rh_pct); // 0x8000/65535 ~= 50%
}

void test_parse_rejects_bad_crc(void) {
  uint8_t f[6] = {0x66, 0x66, 0x00, 0x80, 0x00, 0xAA}; // 错 CRC
  sht30::Sample s;
  TEST_ASSERT_FALSE(sht30::parse(f, &s));
}

void test_rh_clamped_to_100(void) {
  uint8_t f[6] = {0x00, 0x00, 0x00, 0xFF, 0xFF, 0x00};
  f[2] = sht30::crc8(f, 2);
  f[5] = sht30::crc8(f + 3, 2);
  sht30::Sample s;
  TEST_ASSERT_TRUE(sht30::parse(f, &s));
  TEST_ASSERT_EQUAL_FLOAT(100.0f, s.rh_pct);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_crc_datasheet_vector);
  RUN_TEST(test_parse_good_frame);
  RUN_TEST(test_parse_rejects_bad_crc);
  RUN_TEST(test_rh_clamped_to_100);
  return UNITY_END();
}
