#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "uart.h"
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_adc/adc_oneshot.h"
#include "hal/adc_types.h"
#include "driver/gpio.h"
#include "driver/uart.h"

// #define __DBG__
// #define __DBG_UART__

//  LED config
#define LED_GPIO_BLINK 27 //25
#define LED_GPIO_2 25
//  handle config
#define MAX_CONVERSION_FRAME_SIZE 256
#define MAX_POOL_SIZE 1024

//  ADC config
/*
    z pinoutu - GPIO33 = ADC1_5,
    czyli
         @ADC_UNIT = 1, 
         @ADC_CHANNEL = 5
*/
#define ADC_UNIT            ADC_UNIT_1
#define ADC_CHANNEL         ADC_CHANNEL_5
#define ADC_ATTEN           ADC_ATTEN_DB_12
#define ADC_BIT_WIDTH       SOC_ADC_DIGI_MAX_BITWIDTH

//
#define DELAY_MS 2000
#define THR_BASE_UP 100
#define HYSTERESIS_VAL 500

#if defined(__DBG__) || defined(__DBG_UART__)
    #define SAMPLES_COLLECTED 1000
    static const char *TAG = "ADC Sensor Module";
#else
    #define SAMPLES_COLLECTED 1000
#endif

#define ASSERT(val, action) if(!(val)) {action; return;}

typedef struct {
    uint8_t *featuresV;
    adc_oneshot_unit_handle_t adcHandle;
} uart_task_params_t;

void ledFlicker_task(void *pvParameters)
{
    gpio_reset_pin(LED_GPIO_BLINK);
    gpio_set_direction(LED_GPIO_BLINK, GPIO_MODE_OUTPUT);

    gpio_reset_pin(LED_GPIO_2);
    gpio_set_direction(LED_GPIO_2, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_GPIO_2, 1);

    while(1) {
        
        gpio_set_level(LED_GPIO_BLINK, 0); // Wyłącz
        vTaskDelay(pdMS_TO_TICKS(2000));

        gpio_set_level(LED_GPIO_BLINK, 1); // Włącz
        vTaskDelay(pdMS_TO_TICKS(3000));
        
        gpio_set_level(LED_GPIO_BLINK, 0); // Włącz
        vTaskDelay(pdMS_TO_TICKS(2000));
        
        gpio_set_level(LED_GPIO_BLINK, 1); // Wyłącz
        vTaskDelay(pdMS_TO_TICKS(500));
        
        gpio_set_level(LED_GPIO_BLINK, 0); // Włącz
        vTaskDelay(pdMS_TO_TICKS(300));
        
        gpio_set_level(LED_GPIO_BLINK, 1); // Wyłącz
        vTaskDelay(pdMS_TO_TICKS(500));
        
        gpio_set_level(LED_GPIO_BLINK, 0); // Włącz
        vTaskDelay(pdMS_TO_TICKS(500));
        
        gpio_set_level(LED_GPIO_BLINK, 1); // Wyłącz
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}

void uartTask(void *pvParameters)
{
    uart_task_params_t *params = (uart_task_params_t *)pvParameters;

    if (params == NULL) {
        vTaskDelete(NULL);
        return;
    }

    uartConfig();

    uint8_t start = 0xAA;
    uint8_t end = 0xBB;
    int retSum = 0;

    // send START signal
    int ret = uart_write_bytes(UART_NUM_0, &start, sizeof(uint8_t));
    ASSERT(ret, vTaskDelete(NULL));
    
#ifdef __DBG_UART__
for(int i = 0; i < SAMPLES_COLLECTED; i++) {
    static uint8_t test = 0x43; //0x43 = 67
    ret = uart_write_bytes(UART_NUM_0, &test, sizeof(uint8_t));
    ASSERT(ret, vTaskDelete(NULL));
    retSum += ret;
    }
#else
    // send DATA
    ret = uart_write_bytes(UART_NUM_0, params->featuresV, SAMPLES_COLLECTED);
    ASSERT(ret, vTaskDelete(NULL));
#endif

    // send END signal
    ret = uart_write_bytes(UART_NUM_0, &end, sizeof(uint8_t));
    ASSERT(ret, vTaskDelete(NULL));

    if (params->adcHandle != NULL) {
        adc_oneshot_del_unit(params->adcHandle);
    }

    free(params->featuresV);
    free(params);

#ifdef __DBG_UART__
    printf("Written %d bytes\n", retSum);
    fflush(stdout);
#else
    (void)retSum;
#endif

    vTaskDelete(NULL);
}

void app_main(void)
{
    //  Create flickering task for the user 
    //  to repeatedly place the finger on the photoresistor
    if (xTaskCreate(ledFlicker_task, "led", 2048, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE("LED", "Nie udalo sie utworzyc taska LED");
    } 
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_log_level_set("*", ESP_LOG_NONE);
    //  Setup handle for ADC Continuous mode
    //  conv_frame_size and max_store buf_size are default values
    adc_oneshot_unit_handle_t adcHandle;
    const adc_oneshot_unit_init_cfg_t adcHandleCfg = {
        .unit_id = ADC_UNIT,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&adcHandleCfg, &adcHandle));

    adc_oneshot_chan_cfg_t config = {
        .atten = ADC_ATTEN,
        .bitwidth = ADC_BIT_WIDTH,
    };
    //  if it succeeds, ADC is ready to be read from
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adcHandle, ADC_CHANNEL, &config));

#ifdef __DBG__
    ESP_LOGI(TAG, "configured succesfully");
#endif

    //  Set threshold baseline by acquiring 50 raw_data reads and computing the mean
    int baseline = 0;
    for (int i = 0; i < 50; i++) {
        int raw;
        ESP_ERROR_CHECK(adc_oneshot_read(adcHandle, ADC_CHANNEL, &raw));
        baseline += raw;
    }
    baseline /= 50;

    //  final threshold
    int thr = baseline + THR_BASE_UP;
#ifdef __DBG__
    printf("THRESHOLD: %d\n", thr);
#endif
    vTaskDelay(pdMS_TO_TICKS(DELAY_MS));

    uint8_t *featuresV = malloc(SAMPLES_COLLECTED * sizeof(uint8_t));
    //  0x03 = 3 - it should be anything other than 0 and 1
    //  it cannot be 0 nor 1 because they represent actual values while 3 is
    //  easily distinguishable from other read values
    memset(featuresV, 0x03, SAMPLES_COLLECTED);
    for (int i = 0; i < SAMPLES_COLLECTED; i++) {
        int raw;
        ESP_ERROR_CHECK(adc_oneshot_read(adcHandle, ADC_CHANNEL, &raw));

#ifdef __DBG__
        printf("Raw data: %-4u, Value: %d  \n\033[A", raw, raw > thr);
        fflush(stdout);
#endif
        
        featuresV[i] = raw > thr;
        vTaskDelay(pdMS_TO_TICKS(10)); 
    }

#ifdef __DBG__
    printf("\nFINAL FEATURE VECTOR:\n");
    for (int i = 0; i < SAMPLES_COLLECTED; i++) {
        printf("%u", featuresV[i]);
        if ((i + 1) % 50 == 0) {
            printf("\n");
        } else {
            printf(" ");
        }
    }
    printf("\n");
#endif

#ifndef __DBG__
    uart_task_params_t *uartParams = malloc(sizeof(uart_task_params_t));
    if (uartParams != NULL) {
        uartParams->featuresV = featuresV;
        uartParams->adcHandle = adcHandle;
        xTaskCreate(&uartTask, "uartSend", 4096, uartParams, 5, NULL);
    }
#endif
}
