#include <stdint.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_err.h"
#include "driver/uart.h"
#include "uart.h"

#define BAUD_RATE 115200

void uartConfig(void)
{
    const uint32_t uartBufferSize = (1024 * 2);

    //Instalacja drivera UART
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, uartBufferSize, uartBufferSize, 0, NULL, 0));

    const uart_port_t uartPort = UART_NUM_0;
    uart_config_t uartConfigT = {
        .baud_rate = BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };

    //Konfiguracja parametrów drivera
    ESP_ERROR_CHECK(uart_param_config(uartPort, &uartConfigT));

    //
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
}

