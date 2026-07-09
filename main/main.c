#include <stdio.h>
#include <string.h>
#if __has_include("driver/gpio.h")
#include "driver/gpio.h"
#else
#include "sdkconfig.h"
#warning "driver/gpio.h not found, providing minimal stubs for build"
// Minimal stubs so the file can be parsed/compiled when the ESP-IDF
// driver/gpio.h is not available (e.g., in editor/static analysis).
typedef int gpio_num_t;
#define GPIO_MODE_OUTPUT 1
static inline void gpio_reset_pin(int pin) { (void)pin; }
static inline void gpio_set_direction(int pin, int mode) { (void)pin; (void)mode; }
static inline void gpio_set_level(int pin, int level) { (void)pin; (void)level; }
#endif

#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_adc/adc_continuous.h"
#include "hal/adc_types.h"
#include "driver/gpio.h"

// LED config
#define LED_GPIO 25

//handle config
#define MAX_CONVERSION_FRAME_SIZE 256
#define MAX_POOL_SIZE 1024

//ADC config
/*
    z pinoutu - GPIO33 = ADC1_5,
    czyli
         @ADC_UNIT = 1, 
         @ADC_CHANNEL = 5
*/
#define ADC_UNIT            ADC_UNIT_1
#define ADC_CHANNEL         ADC_CHANNEL_5
#define ADC_CONV_MODE       ADC_CONV_SINGLE_UNIT_1
#define ADC_ATTEN           ADC_ATTEN_DB_12
#define ADC_BIT_WIDTH       SOC_ADC_DIGI_MAX_BITWIDTH

//
#define READ_LEN 256
#define READ_TIME 10
#define READ_TIME_TICKS pdMS_TO_TICKS(READ_TIME*1000)
#define SAMPLES_COLLECTED 1000
#define SAMPLE_RATE 20000
#define THRESHOLD 1800

static const char *TAG = "ADC Sensor Module";

/*
    Callback function to be register to the event handler and to be
    called on successful ADC conversion event
    Most likely to send accumulated data through UART
*/
// void cbOnConv()
// {
//     continue;
// }

void ledFlicker_task(void *pvParameters)
{
    gpio_reset_pin(LED_GPIO);

    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    uint8_t gpioLevel = 0;

    while(1) {
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(5000));
        gpio_set_level(LED_GPIO, gpioLevel);
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(1000));
        gpio_set_level(LED_GPIO, gpioLevel);
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(2000));
        gpio_set_level(LED_GPIO, gpioLevel);
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(500));
        gpio_set_level(LED_GPIO, gpioLevel);
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(500));
        gpio_set_level(LED_GPIO, gpioLevel);
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(500));
        gpio_set_level(LED_GPIO, gpioLevel);
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(500));
        gpio_set_level(LED_GPIO, gpioLevel);
        gpioLevel ^= 1;
        vTaskDelay(pdMS_TO_TICKS(5000));
        gpio_set_level(LED_GPIO, gpioLevel);
    }
}


void app_main(void)
{

    // Setup handle for ADC Continuous mode
    // conv_frame_size and max_store buf_size are default values
    adc_continuous_handle_t adcHandle = NULL;
    const adc_continuous_handle_cfg_t adcHandleCfg = {
        .conv_frame_size = MAX_CONVERSION_FRAME_SIZE,
        .max_store_buf_size = MAX_POOL_SIZE,
    };
    ESP_ERROR_CHECK(adc_continuous_new_handle(&adcHandleCfg, &adcHandle));

    adc_digi_pattern_config_t patternCfg = {
        .atten = ADC_ATTEN,
        .bit_width = ADC_BIT_WIDTH,
        .channel = ADC_CHANNEL,
        .unit = ADC_UNIT,
    };
    
    adc_continuous_config_t adcCfg = {
        .pattern_num = 1,
        .adc_pattern = &patternCfg,
        .sample_freq_hz = SAMPLE_RATE,
        .conv_mode = ADC_CONV_MODE,
    };

    ESP_ERROR_CHECK(adc_continuous_config(adcHandle, &adcCfg));
    ESP_LOGI(TAG, "Configuration structs allocated succesfully");

    esp_err_t ret;
    uint32_t retNum = 0;
    uint8_t vStream[READ_LEN] = {0};
    //  0xcc = 204 - it should be anything other than 0
    //  it cannot be 0 because 0 is an actual value while 204 is random
    //  and thus easily distinguishable from other read values
    memset(vStream, 0xcc, READ_LEN);

    // adc_continuous_evt_cbs_t cbS = {
    //     .on_conv_done = cbOnConv,
    // };

    // ESP_ERROR_CHECK(adc_continuous_register_event_callbacks(adcHandle, &cbS, vStream));

    //  Starting ADC
    ESP_ERROR_CHECK(adc_continuous_start(adcHandle));

    xTaskCreate(&ledFlicker_task, "led", 2048, NULL, 5, NULL);
    
    // final feature vector that's later to be sent through UART
    uint8_t *featureVector = malloc(SAMPLES_COLLECTED * sizeof(uint8_t));
    memset(featureVector, 0, SAMPLES_COLLECTED*sizeof(uint8_t));
    uint32_t currentFeatures = 0;
    
    for(int i = 0; currentFeatures < SAMPLES_COLLECTED; i++) {
        ret = adc_continuous_read(adcHandle, vStream, READ_LEN, &retNum, 1000);
        if (ret == ESP_OK) {
            adc_continuous_data_t parsedData[retNum / SOC_ADC_DIGI_RESULT_BYTES];         
            uint32_t numParsedSamples = 0;

            esp_err_t parseRet = adc_continuous_parse_data(adcHandle, vStream, retNum, parsedData, &numParsedSamples);
            if (parseRet == ESP_OK) {
                // ESP_LOGI(TAG, "after read and parse");
                if (numParsedSamples > 0 && parsedData[0].valid) {
                    printf("ADC%d, Chanel: %d, Value: %d, fValue: %-4lu    \n\033[A", 
                        parsedData[0].unit + 1,
                        parsedData[0].channel,
                        parsedData[0].raw_data > THRESHOLD,
                        parsedData[0].raw_data);
                        fflush(stdout);
                } else {
                        ESP_LOGW(TAG, "INVALID DATA [ADC%d, Chanel: %d, Value: %"PRIu32"]",
                            parsedData[0].unit + 1,
                            parsedData[0].channel,
                            parsedData[0].raw_data);
                }
            } else {
                ESP_LOGE(TAG, "Parsing failed");
            }
            // ESP_LOGI(TAG, "Conversion frame ended");
        }
        vTaskDelay(pdMS_TO_TICKS(10));
        
    }
    adc_continuous_stop(adcHandle);
    adc_continuous_deinit(adcHandle);
}
