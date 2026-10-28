/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Audio Spectrum Analyzer with CMSIS-DSP & Flash Optimization
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* USER CODE BEGIN Includes */
#include <stdbool.h>
#include <math.h>

/* CMSIS-DSP Core Includes */
#include "arm_math.h"
#include "arm_const_structs.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef struct {
    uint8_t buffer[4096];
    volatile uint16_t head;
    volatile uint16_t tail;
} RingBuffer;
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define AUDIO_BUFFER_SIZE 4096
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
RingBuffer audio_fifo = { .head = 0, .tail = 0 };
uint8_t rx_data[1];
uint8_t processing_buffer[256];

/* DSP Variables */
float32_t fft_magnitudes[64];
float32_t max_fft_observed = 0.0f;
float32_t lpf_prev_output = 0.0f;
volatile uint32_t packet_counter = 0;

/* Pre-calculated 128-point Hanning Window (Stored in Flash Memory) */
const float32_t hanning_window_128[128] = {
    0.00000000f, 0.00060888f, 0.00243431f, 0.00547025f, 0.00970724f, 0.01513221f, 0.02172828f, 0.02947470f,
    0.03834661f, 0.04831518f, 0.05934759f, 0.07140723f, 0.08445371f, 0.09844309f, 0.11332884f, 0.12906282f,
    0.14559527f, 0.16287582f, 0.18085353f, 0.19947703f, 0.21869460f, 0.23845426f, 0.25870381f, 0.27939103f,
    0.30046380f, 0.32186991f, 0.34355716f, 0.36547343f, 0.38756667f, 0.40978496f, 0.43207641f, 0.45438927f,
    0.47667205f, 0.49887352f, 0.52094285f, 0.54282967f, 0.56448416f, 0.58585695f, 0.60690022f, 0.62756672f,
    0.64781079f, 0.66758763f, 0.68685361f, 0.70556637f, 0.72368481f, 0.74116899f, 0.75798031f, 0.77408162f,
    0.78943734f, 0.80401344f, 0.81777757f, 0.83069905f, 0.84274900f, 0.85389988f, 0.86412595f, 0.87340333f,
    0.88170997f, 0.88902564f, 0.89533190f, 0.90061226f, 0.90485124f, 0.90803522f, 0.91015243f, 0.91119299f,
    0.91119299f, 0.91015243f, 0.90803522f, 0.90485124f, 0.90061226f, 0.89533190f, 0.88902564f, 0.88170997f,
    0.87340333f, 0.86412595f, 0.85389988f, 0.84274900f, 0.83069905f, 0.81777757f, 0.80401344f, 0.78943734f,
    0.77408162f, 0.75798031f, 0.74116899f, 0.72368481f, 0.70556637f, 0.68685361f, 0.66758763f, 0.64781079f,
    0.62756672f, 0.60690022f, 0.58585695f, 0.56448416f, 0.54282967f, 0.52094285f, 0.49887352f, 0.47667205f,
    0.45438927f, 0.43207641f, 0.40978496f, 0.38756667f, 0.36547343f, 0.34355716f, 0.32186991f, 0.30046380f,
    0.27939103f, 0.25870381f, 0.23845426f, 0.21869460f, 0.19947703f, 0.18085353f, 0.16287582f, 0.14559527f,
    0.12906282f, 0.11332884f, 0.09844309f, 0.08445371f, 0.07140723f, 0.05934759f, 0.04831518f, 0.03834661f,
    0.02947470f, 0.02172828f, 0.01513221f, 0.00970724f, 0.00547025f, 0.00243431f, 0.00060888f, 0.00000000f
};
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);

/* USER CODE BEGIN PFP */
void ring_buffer_push(uint8_t data);
void ring_buffer_pop(uint8_t *dest, uint16_t length);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_USART2_UART_Init();

  /* USER CODE BEGIN 2 */
  /* Prime the UART to receive the first byte via Interrupt */
  HAL_UART_Receive_IT(&huart2, rx_data, 1);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
      /* Calculate available unread bytes in the ring buffer */
      uint16_t data_available = (audio_fifo.head >= audio_fifo.tail) ?
                                (audio_fifo.head - audio_fifo.tail) :
                                (AUDIO_BUFFER_SIZE - audio_fifo.tail + audio_fifo.head);

      /* Wait until a full 128-sample frame (256 bytes) is ready */
      if (data_available >= 256) {
          ring_buffer_pop(processing_buffer, 256);

          /* CMSIS-DSP interleaved buffer: [Real, Imag, Real, Imag...] */
          float32_t fft_buffer[256];
          int sample_index = 0;

          /* Low-Pass Filter configuration (alpha = 0.28 sets cutoff fc ~ 1 kHz) */
          const float32_t alpha = 0.28f;

          for (int i = 0; i < 256; i += 2) {
              /* 1. Reconstruct 16-bit PCM integer (Little-Endian) */
              int16_t raw_pcm = (int16_t)((processing_buffer[i+1] << 8) | processing_buffer[i]);

              /* 2. Apply Single-Pole IIR Low-Pass Filter */
              float32_t filtered_sample = (alpha * (float32_t)raw_pcm) + ((1.0f - alpha) * lpf_prev_output);
              lpf_prev_output = filtered_sample;

              /* 3. Windowing (Flash Lookup) */
              /* Multiply the filtered sample by the pre-calculated Hanning array */
              fft_buffer[sample_index * 2] = filtered_sample * hanning_window_128[sample_index]; /* Real */
              fft_buffer[(sample_index * 2) + 1] = 0.0f;                                         /* Imaginary */

              sample_index++;
          }

          /* 4. Execute CMSIS-DSP 128-point Floating-Point FFT */
          arm_cfft_f32(&arm_cfft_sR_f32_len128, fft_buffer, 0, 1);

          /* 5. Extract Complex Magnitudes natively */
          float32_t raw_magnitudes[64];
          arm_cmplx_mag_f32(fft_buffer, raw_magnitudes, 64);

          /* 6. Normalize */
          for (int i = 0; i < 64; i++) {
              /* Divide by N/2 (64) to scale array back to PCM16 range */
              float32_t current_mag = raw_magnitudes[i] / 64.0f;
              fft_magnitudes[i] = current_mag;

              if (current_mag > max_fft_observed) {
                  max_fft_observed = current_mag;
              }
          }

          /* 7. Transmit FFT Data back to PC for Visualization */
          uint8_t sync_header[4] = {0xAA, 0xBB, 0xCC, 0xDD};
          HAL_UART_Transmit(&huart2, sync_header, 4, 10);
          HAL_UART_Transmit(&huart2, (uint8_t*)fft_magnitudes, sizeof(fft_magnitudes), 50);
      }
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI_DIV2;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL16;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 460800;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI15_10_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);

}

/* USER CODE BEGIN 4 */
void ring_buffer_push(uint8_t data) {
    uint16_t next_head = (audio_fifo.head + 1) % AUDIO_BUFFER_SIZE;
    if (next_head != audio_fifo.tail) {
        audio_fifo.buffer[audio_fifo.head] = data;
        audio_fifo.head = next_head;
    }
}

void ring_buffer_pop(uint8_t *dest, uint16_t length) {
    for (uint16_t i = 0; i < length; i++) {
        dest[i] = audio_fifo.buffer[audio_fifo.tail];
        audio_fifo.tail = (audio_fifo.tail + 1) % AUDIO_BUFFER_SIZE;
    }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        ring_buffer_push(rx_data[0]);

        packet_counter++;
        /* Toggle LED to confirm data ingestion */
        if (packet_counter >= 250) {
            HAL_GPIO_TogglePin(LD2_GPIO_Port, LD2_Pin);
            packet_counter = 0;
        }

        /* Re-prime the interrupt for the next byte */
        HAL_UART_Receive_IT(&huart2, rx_data, 1);
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        /* Clear UART Overrun (ORE) flags manually if data arrives too fast */
        volatile uint32_t tmpreg = 0x00U;
        tmpreg = huart->Instance->SR;
        tmpreg = huart->Instance->DR;
        (void)tmpreg;

        huart->ErrorCode = HAL_UART_ERROR_NONE;
        huart->RxState = HAL_UART_STATE_READY;

        HAL_UART_Receive_IT(&huart2, rx_data, 1);
    }
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
