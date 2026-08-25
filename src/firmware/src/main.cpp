// ESP-IDF 版 SHT30 温湿度记录仪（G9 修复：Arduino→IDF 迁移）
// 控制台：USB-Serial-JTAG（sdkconfig.defaults 对齐 Wokwi serialInterface 属性）
// 引脚：SDA=GPIO4, SCL=GPIO5（与 intent_v1 一致，避开 strapping 脚）
#include <cstdio>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"
#include "sht30.h"

static constexpr uint8_t SHT_ADDR = sht30::DEFAULT_ADDR;
static constexpr gpio_num_t PIN_SDA = GPIO_NUM_4;
static constexpr gpio_num_t PIN_SCL = GPIO_NUM_5;
static uint32_t g_seq = 0;

#ifdef SIM_STUB_SENSOR
// Wokwi 无 SHT31 零件：仿真构建合成确定性样本（证据级 B：仅验证固件管线/JSON/时序）
static bool readSHT30(sht30::Sample* out) {
  out->temp_c = 25.00f + static_cast<float>(g_seq % 10) * 0.1f;
  out->rh_pct = 50.0f + static_cast<float>(g_seq % 5);
  out->ok = true;
  vTaskDelay(pdMS_TO_TICKS(20));
  return true;
}
#else
static i2c_master_dev_handle_t s_dev = nullptr;

static bool i2c_init() {
  i2c_master_bus_config_t bus = {};
  bus.i2c_port = I2C_NUM_0;
  bus.sda_io_num = PIN_SDA;
  bus.scl_io_num = PIN_SCL;
  bus.clk_source = I2C_CLK_SRC_DEFAULT;
  bus.glitch_ignore_cnt = 7;
  bus.flags.enable_internal_pullup = true; // 板上另有 4.7k 外部上拉
  i2c_master_bus_handle_t bus_h = nullptr;
  if (i2c_new_master_bus(&bus, &bus_h) != ESP_OK) return false;

  i2c_device_config_t dev = {};
  dev.dev_addr_length = I2C_ADDR_BIT_LEN_7;
  dev.device_address = SHT_ADDR;
  dev.scl_speed_hz = 100000;
  return i2c_master_bus_add_device(bus_h, &dev, &s_dev) == ESP_OK;
}

static bool readSHT30(sht30::Sample* out) {
  const uint8_t cmd[2] = {0x2C, 0x06}; // 单次测量、高重复性、时钟拉伸
  if (i2c_master_transmit(s_dev, cmd, sizeof(cmd), -1) != ESP_OK) return false;
  vTaskDelay(pdMS_TO_TICKS(20)); // 测量时间 max ~15ms
  uint8_t raw[6];
  if (i2c_master_receive(s_dev, raw, sizeof(raw), -1) != ESP_OK) return false;
  return sht30::parse(raw, out);
}
#endif

extern "C" void app_main(void) {
#ifdef SIM_STUB_SENSOR
  printf("{\"boot\":\"sht30-logger-idf\",\"ver\":2,\"mode\":\"simstub\"}\n");
#else
  printf("{\"boot\":\"sht30-logger-idf\",\"ver\":2}\n");
  if (!i2c_init()) {
    printf("{\"err\":\"i2c_init\"}\n");
  }
#endif

  for (;;) {
    sht30::Sample s;
    ++g_seq;
    // 整数化输出：规避 newlib nano 格式不支持 %f 的坑
    if (readSHT30(&s)) {
      long t_i = static_cast<long>(s.temp_c * 100.0f + (s.temp_c >= 0 ? 0.5f : -0.5f));
      long h_i = static_cast<long>(s.rh_pct * 10.0f + 0.5f);
      printf("{\"seq\":%lu,\"t_c\":%ld.%02ld,\"rh\":%ld.%ld}\n",
             static_cast<unsigned long>(g_seq), t_i / 100, labs(t_i) % 100,
             h_i / 10, h_i % 10);
    } else {
      printf("{\"seq\":%lu,\"err\":\"sht30_read\"}\n",
             static_cast<unsigned long>(g_seq));
    }
    vTaskDelay(pdMS_TO_TICKS(2000));
  }
}
