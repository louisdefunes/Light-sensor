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
#include "esp_system.h"
#include "esp_random.h"

#define __DBG__
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
#define DELAY_MS 1000
#define THR_BASE_UP 100
#define HYSTERESIS_VAL 200
#define BASELINE_SAMPLE_COUNT 100

#define SAMPLE_ACQUISITON_TIME 10000 // 10k ms = 10s
#define MAX_RAND_SAMPLES 200
#define MIN_RAND_SAMPLES 40

#if defined(__DBG__) || defined(__DBG_UART__)
    #define SAMPLES_COLLECTED 1000
    static const char *TAG = "ADC Sensor Module";
#else
    #define SAMPLES_COLLECTED 1000
#endif

#define ASSERT(val, action) do { if (!(val)) { action; return; } } while (0)

typedef struct {
    uint8_t *userSignal;
    uint8_t *refSignal;
} measurement_t;

typedef struct {
    measurement_t measurement;
    adc_oneshot_unit_handle_t adcHandle;
} uart_task_params_t;

uint32_t inline random_phased_number(uint32_t max, uint32_t min) {
    return ((esp_random() % (max - min + 1)) + min);
}

uint8_t *genRandomPattern(void) {
    uint8_t *pattern = malloc(SAMPLES_COLLECTED);
    if (pattern == NULL) {
        return NULL;
    }

    uint32_t remaining = SAMPLES_COLLECTED;
    uint8_t state = 0;

    uint8_t *cursor = pattern;
    
    while(remaining > 0) {
        uint32_t phase = 
            random_phased_number(MAX_RAND_SAMPLES, MIN_RAND_SAMPLES);

        if (phase > remaining) {
            phase = remaining;
        }
        memset(cursor, state, phase);
        cursor += phase;
        remaining -= phase;
        state = !state;
    }
    return pattern;
}

static void acquire_measurement(
    measurement_t *measurement,
    adc_oneshot_unit_handle_t adcHandle,
    uint32_t thrUpp,
    uint32_t thrLow)
{
    gpio_reset_pin(LED_GPIO_BLINK);
    gpio_set_direction(LED_GPIO_BLINK, GPIO_MODE_OUTPUT);

    gpio_reset_pin(LED_GPIO_2);
    gpio_set_direction(LED_GPIO_2, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_GPIO_2, 1);

    uint32_t current_state = 0;
    TickType_t nextSampleTime = xTaskGetTickCount();

    for (uint32_t i = 0; i < SAMPLES_COLLECTED; i++) {
        gpio_set_level(LED_GPIO_BLINK, measurement->refSignal[i]);

        int raw;
        ESP_ERROR_CHECK(adc_oneshot_read(adcHandle, ADC_CHANNEL, &raw));

#ifdef __DBG__
        printf("Raw data: %-4d, Current State: %lu  \n\033[A",
               raw, (unsigned long)current_state);
        fflush(stdout);
#endif

        if ((uint32_t)raw >= thrUpp) {
            current_state = 1;
        } else if ((uint32_t)raw <= thrLow) {
            current_state = 0;
        }

        measurement->userSignal[i] = (uint8_t)current_state;
        vTaskDelayUntil(&nextSampleTime, pdMS_TO_TICKS(10));
    }

#ifdef __DBG__
    printf("\nFINAL FEATURE VECTOR:\n");
    for (uint32_t i = 0; i < SAMPLES_COLLECTED; i++) {
        printf("%u", measurement->userSignal[i]);
        if ((i + 1) % 50 == 0) {
            printf("\n");
        } else {
            printf(" ");
        }
    }
    printf("\n");
#endif
}

void uartTask(void *pvParameters)
{
    uart_task_params_t *params = pvParameters;
    ASSERT(params, vTaskDelete(NULL));

    uartConfig();

    uint8_t start = 0xAA;
    uint8_t end = 0xBB;
    uint32_t retSum = 0;

    // send START signal
    int ret = uart_write_bytes(UART_NUM_0, &start, sizeof(uint8_t));
    ASSERT(ret, vTaskDelete(NULL));
    
#ifdef __DBG_UART__
for(uint32_t i = 0; i < SAMPLES_COLLECTED; i++) {
    static uint8_t test = 0x43; //0x43 = 67
    ret = uart_write_bytes(UART_NUM_0, &test, sizeof(uint8_t));
    ASSERT(ret, vTaskDelete(NULL));
    retSum += ret;
    }
#else
    // send USER DATA
    ret = uart_write_bytes(UART_NUM_0, params->measurement.userSignal, SAMPLES_COLLECTED);
    ASSERT(ret == SAMPLES_COLLECTED, vTaskDelete(NULL));

    // send REFERENCE DATA
    ret = uart_write_bytes(UART_NUM_0, params->measurement.refSignal, SAMPLES_COLLECTED);
    ASSERT(ret == SAMPLES_COLLECTED, vTaskDelete(NULL));
#endif

    // send END signal
    ret = uart_write_bytes(UART_NUM_0, &end, sizeof(uint8_t));
    ASSERT(ret, vTaskDelete(NULL));

    if (params->adcHandle != NULL) {
        adc_oneshot_del_unit(params->adcHandle);
    }

    free(params->measurement.userSignal);
    free(params->measurement.refSignal);
    free(params);

#ifdef __DBG_UART__
    printf("Written %d bytes\n", retSum);
    fflush(stdout);
#else
    (void)retSum;
#endif
    ESP_ERROR_CHECK(uart_wait_tx_done(UART_NUM_0, pdMS_TO_TICKS(1000)));
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
    vTaskDelete(NULL);
}

void app_main(void)
{
    measurement_t *measurement = malloc(sizeof(measurement_t));
    ASSERT(measurement, );

    measurement->userSignal = malloc(SAMPLES_COLLECTED * sizeof(uint8_t));
    measurement->refSignal = genRandomPattern();

    vTaskDelay(pdMS_TO_TICKS(DELAY_MS));
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
    uint32_t baseline = 0;
    for (uint32_t i = 0; i < BASELINE_SAMPLE_COUNT; i++) {
        int raw;
        ESP_ERROR_CHECK(adc_oneshot_read(adcHandle, ADC_CHANNEL, &raw));
        baseline += raw;
    }
    baseline /= BASELINE_SAMPLE_COUNT;

    //  final thresholds, hysteresis value added to thrLow found experimentally
    uint32_t thrUpp = baseline + HYSTERESIS_VAL;
    uint32_t thrLow = baseline + (HYSTERESIS_VAL * 0.7);
#ifdef __DBG__
    printf("UPPER THRESHOLD: %ld\n", thrUpp);
    printf("LOWER THRESHOLD: %ld\n", thrLow);
#endif
    vTaskDelay(pdMS_TO_TICKS(DELAY_MS));

    memset(measurement->userSignal, 0x03, SAMPLES_COLLECTED);

    acquire_measurement(measurement, adcHandle, thrUpp, thrLow);

#ifndef __DBG__
    uart_task_params_t *uartParams = malloc(sizeof(uart_task_params_t));
    if (uartParams != NULL) {
        uartParams->measurement = *measurement;
        uartParams->adcHandle = adcHandle;
         if (xTaskCreate(&uartTask, 
                        "uartSend", 
                        4096, 
                        uartParams, 
                        5,
                        NULL) == pdPASS) {
            free(measurement);
         } else {
            free(uartParams);
            free(measurement->userSignal);
            free(measurement->refSignal);
            adc_oneshot_del_unit(adcHandle);
            free(measurement);
         }
    }
#endif
}
