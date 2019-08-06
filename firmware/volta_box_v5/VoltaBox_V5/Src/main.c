
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * This notice applies to any and all portions of this file
  * that are not between comment pairs USER CODE BEGIN and
  * USER CODE END. Other portions of this file, whether 
  * inserted by the user or by software development tools
  * are owned by their respective copyright owners.
  *
  * Copyright (c) 2018 STMicroelectronics International N.V. 
  * All rights reserved.
  *
  * Redistribution and use in source and binary forms, with or without 
  * modification, are permitted, provided that the following conditions are met:
  *
  * 1. Redistribution of source code must retain the above copyright notice, 
  *    this list of conditions and the following disclaimer.
  * 2. Redistributions in binary form must reproduce the above copyright notice,
  *    this list of conditions and the following disclaimer in the documentation
  *    and/or other materials provided with the distribution.
  * 3. Neither the name of STMicroelectronics nor the names of other 
  *    contributors to this software may be used to endorse or promote products 
  *    derived from this software without specific written permission.
  * 4. This software, including modifications and/or derivative works of this 
  *    software, must execute solely and exclusively on microcontroller or
  *    microprocessor devices manufactured by or for STMicroelectronics.
  * 5. Redistribution and use of this software other than as permitted under 
  *    this license is void and will automatically terminate your rights under 
  *    this license. 
  *
  * THIS SOFTWARE IS PROVIDED BY STMICROELECTRONICS AND CONTRIBUTORS "AS IS" 
  * AND ANY EXPRESS, IMPLIED OR STATUTORY WARRANTIES, INCLUDING, BUT NOT 
  * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
  * PARTICULAR PURPOSE AND NON-INFRINGEMENT OF THIRD PARTY INTELLECTUAL PROPERTY
  * RIGHTS ARE DISCLAIMED TO THE FULLEST EXTENT PERMITTED BY LAW. IN NO EVENT 
  * SHALL STMICROELECTRONICS OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
  * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
  * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, 
  * OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
  * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING 
  * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
  * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
  *
  ******************************************************************************
  */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "stm32f1xx_hal.h"
#include "fatfs.h"
#include "usb_device.h"

/* USER CODE BEGIN Includes */
#include "usbd_cdc_if.h"
#include "buffer.h"
#include "cp1251.h"

#define SENDBUF_SIZE rb.size>>1

#define fontSizeX 5
#define fontSizeY 8

#define scrSizeX 128
#define scrSizeY 64

#define cNum scrSizeX/fontSizeX
#define lNum scrSizeY/fontSizeY

#define printClearL	1

#define bufSizeForUSB	32
#define bufSizeForCard	4096
/* USER CODE END Includes */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c2;

SD_HandleTypeDef hsd;
DMA_HandleTypeDef hdma_sdio;

SPI_HandleTypeDef hspi1;
SPI_HandleTypeDef hspi2;
SPI_HandleTypeDef hspi3;
DMA_HandleTypeDef hdma_spi2_rx;
DMA_HandleTypeDef hdma_spi2_tx;
DMA_HandleTypeDef hdma_spi3_rx;
DMA_HandleTypeDef hdma_spi3_tx;

TIM_HandleTypeDef htim3;

DMA_HandleTypeDef hdma_memtomem_dma1_channel1;

/* USER CODE BEGIN PV */
/* Private variables ---------------------------------------------------------*/
const char *errMsg[20]={"FR_OK", "FR_DISK_ERR", "FR_INT_ERR", "FR_NOT_READY", "FR_NO_FILE",
	  	    			"FR_NO_PATH", "FR_INVALID_NAME", "FR_DENIED", "FR_EXIST", "FR_INVALID_OBJECT",
	  	    			"FR_WRITE_PROTECTED", "FR_INVALID_DRIVE", "FR_NOT_ENABLED","FR_NO_FILESYSTEM",
	  	    			"FR_MKFS_ABORTED", "FR_TIMEOUT", "FR_LOCKED", "FR_NOT_ENOUGH_CORE",
	  	    			"FR_TOO_MANY_OPEN_FILES", "FR_INVALID_PARAMETER"};
const uint8_t cmd_read_current[] = { 0x03, 0x82, 0x00, 0x00 };
const uint8_t cmd_read_voltage[] = { 0x01, 0x82, 0x00, 0x00 };
const uint8_t cmd_read[] = { 0x03, 0x82, 0x00, 0x00, 0x00, 0x00 };
struct ringbuf_t rb;
int isCardHere = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_SPI1_Init(void);
static void MX_SPI2_Init(void);
static void MX_SPI3_Init(void);
static void MX_TIM3_Init(void);
static void MX_I2C2_Init(void);
static void MX_SDIO_SD_Init(void);

/* USER CODE BEGIN PFP */
/* Private function prototypes -----------------------------------------------*/

/* USER CODE END PFP */

/* USER CODE BEGIN 0 */
void delay(int t)
{
  while(t--) __asm("nop");
}

uint16_t overSampleISum = 0;
uint16_t overSampleUSum = 0;
//uint8_t overSampleCount = 0;

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim) {
  if (htim->Instance == TIM3) {
	  uint8_t receive_buffer[4];// = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };

	  int i;
	  for(i = 0; i < 4 * (~isCardHere&0b1) + isCardHere; i++)
	  {
		  HAL_GPIO_WritePin(SPI2_NSS_GPIO_Port, SPI2_NSS_Pin, GPIO_PIN_RESET);
		  HAL_SPI_TransmitReceive(&hspi2, cmd_read_current, receive_buffer,	2, HAL_MAX_DELAY);
		  HAL_GPIO_WritePin(SPI2_NSS_GPIO_Port, SPI2_NSS_Pin, GPIO_PIN_SET);
		  uint16_t current_value = ((uint16_t) receive_buffer[3] << 8) + (uint16_t) receive_buffer[2];
		  HAL_GPIO_WritePin(SPI2_NSS_GPIO_Port, SPI2_NSS_Pin, GPIO_PIN_RESET);
		  HAL_SPI_TransmitReceive(&hspi2, cmd_read_voltage, receive_buffer, 2, HAL_MAX_DELAY);
		  HAL_GPIO_WritePin(SPI2_NSS_GPIO_Port, SPI2_NSS_Pin, GPIO_PIN_SET);
		  uint16_t voltage_value = ((uint16_t) receive_buffer[3] << 8) + (uint16_t) receive_buffer[2];
		  overSampleISum += current_value;
		  overSampleUSum += voltage_value;
		//delay(50);//@72MHz
	  }
	  rb_push(&rb, overSampleISum);
	  //rb_push(&rb, overSampleUSum);
	  overSampleISum = 0;
	  overSampleUSum = 0;

	  /*if(overSampleCount < 4 * ~isCardHere&0b1 + isCardHere)
	  {
		rb_push(&rb, overSampleISum);
		//rb_push(&rb, overSampleUSum);
		overSampleISum = 0;
		overSampleUSum = 0;
	  }
	  else
	  {
		  overSampleCount++;
	  }*/

	  //GPIOA->BSRR = SPI2_NSS_Pin;



  }
}

void fSetCurTime(TCHAR* fname)
{
  /*FILINFO fTime;
  RTC_TimeTypeDef curTime;
  RTC_DateTypeDef curDate;
  HAL_RTC_GetTime(&hrtc, &curTime, RTC_FORMAT_BIN);
  HAL_RTC_GetDate(&hrtc, &curDate, RTC_FORMAT_BIN);
  fTime.fdate = (WORD)(((curDate.Year - 1980) * 512U) | curDate.Month * 32U | curDate.Date);
  fTime.ftime = (WORD)(curTime.Hours * 2048U | curTime.Minutes * 32U | curTime.Seconds / 2U);
  f_utime(fname, &fTime);*/
}

uint8_t curX=0, curY=0;
void print(char *text, uint8_t posC, uint8_t posL, uint8_t *scr, uint8_t flag)
{
	int i;
	if(flag&printClearL)
	{
		for(i = 0; i < 128; i++)
			scr[posL*scrSizeX + i] = 0;
	}
	for(i = 0; text[i]!='\0'; i++)
	{
		int x;
		for(x = 0; x < fontSizeX; x++)
			scr[posL*scrSizeX + posC*fontSizeX + x] = sym[text[i]*fontSizeX + x];
		posC++;
	}
}

void oledInit()
{
	uint8_t data[5] = {0x8D, 0x14, 0xAF, 0x20, 0x00};
	GPIOA->BSRR = OLED_CS_Pin << 16;
	GPIOB->BSRR = OLED_DC_Pin << 16 | OLED_RS_Pin << 16;
	HAL_Delay(0);
	GPIOB->BSRR = OLED_RS_Pin;
	HAL_SPI_Transmit(&hspi3, data, sizeof(data), 1000);
}
uint8_t scr[1024];
void oledUpdate(uint8_t *screen)
{
	GPIOA->BSRR = OLED_CS_Pin << 16;
	GPIOB->BSRR = OLED_DC_Pin;
	HAL_SPI_Transmit_DMA(&hspi3, screen, 1024);											//TODO ENABLE UPDATE
}

uint8_t logC, logL, logStartL = 0, logLCount = 0;
int8_t logOldL = 0;
char logData[8][26];//25 Actually + 1 for null character

void toLog(char *msg)
{
	int i;
	if(logLCount > 7)
	{
		if(logOldL > 7)
			logOldL = 0;
		strcpy(logData[logOldL], msg);
		int L = 0;
		for(i = logOldL+1; i < 8; i++, L++)
			print(logData[i], 0, L, scr, printClearL);
		for(i = 0; i < logOldL+1; i++, L++)
			print(logData[i], 0, L, scr, printClearL);
		logOldL++;
	}
	else
	{
		logLCount++;
		strcpy(logData[logLCount-1], msg);
		print(msg, 0, logLCount-1, scr, printClearL);
	}
}

void testScr(uint8_t *screen)
{
	int i;
	for(i = 0; i < 1024; i++)
	{
		scr[i]=0xAA;
		i++;
		scr[i]=0x55;
	}
}

void clrScreen(uint8_t *screen)
{
	int i;
	for(i = 0; i < 1024; i++)
		screen[i] = 0x00;
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  *
  * @retval None
  */
int main(void)
{
  /* USER CODE BEGIN 1 */
	  uint16_t *buff;// = (uint16_t*)malloc(bufSizeForCard);

  /* USER CODE END 1 */

  /* MCU Configuration----------------------------------------------------------*/

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
  MX_DMA_Init();
  MX_SPI1_Init();
  MX_SPI2_Init();
  MX_SPI3_Init();
  MX_USB_DEVICE_Init();
  MX_TIM3_Init();
  MX_I2C2_Init();
  MX_SDIO_SD_Init();
  MX_FATFS_Init();
  /* USER CODE BEGIN 2 */
  oledInit();
  clrScreen(scr);
  print("VoltaBox_v5", 5, 2, scr, 0);
  //priint("14bit/10kHz in USB", 0, 3, scr, 0);
  oledUpdate(scr);

  FATFS sdFiles;
  FIL test;
  FIL measureStat;
  int ret;

  /*toLog("Sheep counter v5.");
  oledUpdate(scr);
  HAL_Delay(500);
  int sheep = 0;
  while(1)
  {
	  char tmp[25];
	  sprintf(tmp, "Counting sheep %d", sheep);
	  toLog(tmp);
	  oledUpdate(scr);
	  HAL_Delay(500);
	  sheep++;
  }*/

  unsigned int writtenCount;
  if(f_mount(&sdFiles, SDPath, 1)==FR_OK)
  {
	  toLog("Sdcard found!");
	  toLog("f_mount OK");
	  oledUpdate(scr);
	  int i;
	  char fname[16];
	  for(i = 0; i < 999; i++)
	  {
		  sprintf(fname, "MEASURE.%03d", i);
		  int status = f_stat(fname, NULL);
	  	  if(status==FR_NO_FILE)
	  		  break;
	  }
	  if(f_open(&measureStat, fname, FA_WRITE | FA_CREATE_ALWAYS) == FR_OK)
	  {
		  char tmp[25];
		  sprintf(tmp, "%s created!", fname);
		  toLog(tmp);
		  oledUpdate(scr);
		  //f_write(&measureStat, "Start\n", 6, &writtenCount);//TODO: d4$
		  //f_sync(&measureStat);
		  //f_write(&measureStat, "Test\n", 5, &writtenCount);
		  //f_sync(&measureStat);

		  isCardHere = 1;
	  }
  }
  else
  {
	  ret = f_mkfs(SDPath, 0, 0);
  }

  // wait USB enumeration
  HAL_Delay(1000);


//  testScr(scr);
  //print("Test", 3, 3, scr);
  //oledUpdate(scr);
  HAL_TIM_Base_Start_IT(&htim3);
  if(!isCardHere)
  {
	  rb_init(&rb, bufSizeForUSB);
	  buff = (uint16_t*)malloc(bufSizeForUSB);
	  toLog("USB mode. TIM3 started.");
  }
  else
  {
	  rb_init(&rb, bufSizeForCard);
	  buff = (uint16_t*)malloc(bufSizeForCard);
	  //htim3.Init.Prescaler = 719;//																TODO добавить 9-ку.
	  //HAL_TIM_Base_Init(&htim3);
	  toLog("SD mode. TIM3 started.");
  }
  oledUpdate(scr);

 // uint32_t gpioPattern[8]={SPI2_NSS_Pin, SPI2_NSS_Pin << 16, SPI2_NSS_Pin, SPI2_NSS_Pin << 16, SPI2_NSS_Pin, SPI2_NSS_Pin << 16, SPI2_NSS_Pin, SPI2_NSS_Pin << 16};
  //while(1)
//	  HAL_DMA_Start(&hdma_memtomem_dma1_channel1, gpioPattern, &SPI2_NSS_GPIO_Port->BSRR, 8);

  /*while(1)																	//УБРАТЬ
  {
	  f_write(&measureStat, "Test\n", 5, &writtenCount);
	  f_sync(&measureStat);
	  HAL_Delay(1000);

  }*/
  //TIM_CCxChannelCmd()

  //HAL_DMA_
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */

  uint16_t syncTimer = 0, sCount = 0, eCount = 0;
  while (1)
  {

  /* USER CODE END WHILE */

  /* USER CODE BEGIN 3 */

	  uint8_t status;
	  if (rb_remain(&rb) > SENDBUF_SIZE) {
		  	  int i;
	  	      for (i = 0; i < SENDBUF_SIZE; i++)
	  	        buff[i] = rb_pop(&rb);
	  	      if(!isCardHere){
	  	    	while (CDC_Transmit_FS((uint8_t*) buff, bufSizeForUSB) == USBD_BUSY);
	  	      }
	  	      else
	  	      {
	  	    	status = f_write(&measureStat, (uint8_t*) buff, bufSizeForCard, &writtenCount);
	  	    	if(status !=FR_OK)
	  	    	{
	  	    		toLog("Something happened:");
					toLog("f_write returned:");
					toLog(errMsg[status]);
	  	    		status = f_write(&measureStat + writtenCount, (uint8_t*) buff, bufSizeForCard - writtenCount, &writtenCount);
	  	    		if(status!=FR_OK)
					{
	  	    			toLog("Retrying");
						toLog("f_write returned:");
						toLog(errMsg[status]);
						HAL_TIM_Base_Stop(&htim3);
						char tmp[21];
						sprintf(tmp, "Writes = %d", sCount);
						toLog(tmp);
						sprintf(tmp, "Errors = %d", eCount);
						toLog(tmp);
					}
	  	    		oledUpdate(scr);
	  	    	}
	  	    	if(syncTimer == 16)
	  	    	{
	  	    		status = f_sync(&measureStat);
	  	    		char tmp[25];
	  	    		if(status == FR_OK)
	  	    		{
	  	    			sCount++;
	  	    			sprintf(tmp, "SD success No %d.", sCount);
	  	    			toLog(tmp);
	  	    		}
	  	    		else
	  	    		{
	  	    			eCount++;
	  	    			sprintf(tmp, "SD error No %d", eCount);
	  	    			toLog(errMsg[status]);
						toLog(tmp);
	  	    		}
	  	    		oledUpdate(scr);
	  	    		syncTimer = 0;
	  	    	}
	  	    	else
	  	    		syncTimer++;
	  	      }
	  }
  }
  /* USER CODE END 3 */

}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{

  RCC_OscInitTypeDef RCC_OscInitStruct;
  RCC_ClkInitTypeDef RCC_ClkInitStruct;
  RCC_PeriphCLKInitTypeDef PeriphClkInit;

    /**Initializes the CPU, AHB and APB busses clocks 
    */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

    /**Initializes the CPU, AHB and APB busses clocks 
    */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_USB;
  PeriphClkInit.UsbClockSelection = RCC_USBCLKSOURCE_PLL_DIV1_5;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

    /**Configure the Systick interrupt time 
    */
  HAL_SYSTICK_Config(HAL_RCC_GetHCLKFreq()/1000);

    /**Configure the Systick 
    */
  HAL_SYSTICK_CLKSourceConfig(SYSTICK_CLKSOURCE_HCLK);

  /* SysTick_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(SysTick_IRQn, 0, 0);
}

/* I2C2 init function */
static void MX_I2C2_Init(void)
{

  hi2c2.Instance = I2C2;
  hi2c2.Init.ClockSpeed = 100000;
  hi2c2.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c2.Init.OwnAddress1 = 0;
  hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c2.Init.OwnAddress2 = 0;
  hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c2) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

}

/* SDIO init function */
static void MX_SDIO_SD_Init(void)
{

  hsd.Instance = SDIO;
  hsd.Init.ClockEdge = SDIO_CLOCK_EDGE_RISING;
  hsd.Init.ClockBypass = SDIO_CLOCK_BYPASS_DISABLE;
  hsd.Init.ClockPowerSave = SDIO_CLOCK_POWER_SAVE_DISABLE;
  hsd.Init.BusWide = SDIO_BUS_WIDE_1B;
  hsd.Init.HardwareFlowControl = SDIO_HARDWARE_FLOW_CONTROL_DISABLE;
  hsd.Init.ClockDiv = 16;

}

/* SPI1 init function */
static void MX_SPI1_Init(void)
{

  /* SPI1 parameter configuration*/
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_MASTER;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
  hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_4;
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.CRCPolynomial = 10;
  if (HAL_SPI_Init(&hspi1) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

}

/* SPI2 init function */
static void MX_SPI2_Init(void)
{

  /* SPI2 parameter configuration*/
  hspi2.Instance = SPI2;
  hspi2.Init.Mode = SPI_MODE_MASTER;
  hspi2.Init.Direction = SPI_DIRECTION_2LINES;
  hspi2.Init.DataSize = SPI_DATASIZE_16BIT;
  hspi2.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi2.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi2.Init.NSS = SPI_NSS_SOFT;
  hspi2.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_2;
  hspi2.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi2.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi2.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi2.Init.CRCPolynomial = 10;
  if (HAL_SPI_Init(&hspi2) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

}

/* SPI3 init function */
static void MX_SPI3_Init(void)
{

  /* SPI3 parameter configuration*/
  hspi3.Instance = SPI3;
  hspi3.Init.Mode = SPI_MODE_MASTER;
  hspi3.Init.Direction = SPI_DIRECTION_1LINE;
  hspi3.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi3.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi3.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi3.Init.NSS = SPI_NSS_SOFT;
  hspi3.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_4;
  hspi3.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi3.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi3.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi3.Init.CRCPolynomial = 10;
  if (HAL_SPI_Init(&hspi3) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

}

/* TIM3 init function */
static void MX_TIM3_Init(void)
{

  TIM_ClockConfigTypeDef sClockSourceConfig;
  TIM_MasterConfigTypeDef sMasterConfig;

  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 719;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 9;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim3) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim3, &sClockSourceConfig) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

}

/** 
  * Enable DMA controller clock
  * Configure DMA for memory to memory transfers
  *   hdma_memtomem_dma1_channel1
  */
static void MX_DMA_Init(void) 
{
  /* DMA controller clock enable */
  __HAL_RCC_DMA1_CLK_ENABLE();
  __HAL_RCC_DMA2_CLK_ENABLE();

  /* Configure DMA request hdma_memtomem_dma1_channel1 on DMA1_Channel1 */
  hdma_memtomem_dma1_channel1.Instance = DMA1_Channel1;
  hdma_memtomem_dma1_channel1.Init.Direction = DMA_MEMORY_TO_MEMORY;
  hdma_memtomem_dma1_channel1.Init.PeriphInc = DMA_PINC_ENABLE;
  hdma_memtomem_dma1_channel1.Init.MemInc = DMA_MINC_DISABLE;
  hdma_memtomem_dma1_channel1.Init.PeriphDataAlignment = DMA_PDATAALIGN_WORD;
  hdma_memtomem_dma1_channel1.Init.MemDataAlignment = DMA_MDATAALIGN_WORD;
  hdma_memtomem_dma1_channel1.Init.Mode = DMA_NORMAL;
  hdma_memtomem_dma1_channel1.Init.Priority = DMA_PRIORITY_LOW;
  if (HAL_DMA_Init(&hdma_memtomem_dma1_channel1) != HAL_OK)
  {
    _Error_Handler(__FILE__, __LINE__);
  }

  /* DMA interrupt init */
  /* DMA1_Channel4_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel4_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel4_IRQn);
  /* DMA1_Channel5_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel5_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel5_IRQn);
  /* DMA2_Channel1_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA2_Channel1_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA2_Channel1_IRQn);
  /* DMA2_Channel2_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA2_Channel2_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA2_Channel2_IRQn);
  /* DMA2_Channel4_5_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA2_Channel4_5_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA2_Channel4_5_IRQn);

}

/** Configure pins as 
        * Analog 
        * Input 
        * Output
        * EVENT_OUT
        * EXTI
*/
static void MX_GPIO_Init(void)
{

  GPIO_InitTypeDef GPIO_InitStruct;

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, SPI2_NSS_Pin|OLED_RS_Pin|OLED_DC_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(OLED_CS_GPIO_Port, OLED_CS_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pins : SPI2_NSS_Pin OLED_RS_Pin OLED_DC_Pin */
  GPIO_InitStruct.Pin = SPI2_NSS_Pin|OLED_RS_Pin|OLED_DC_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /*Configure GPIO pin : OLED_CS_Pin */
  GPIO_InitStruct.Pin = OLED_CS_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(OLED_CS_GPIO_Port, &GPIO_InitStruct);

}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @param  file: The file name as string.
  * @param  line: The line in file as a number.
  * @retval None
  */
void _Error_Handler(char *file, int line)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  while(1)
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
void assert_failed(uint8_t* file, uint32_t line)
{ 
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     tex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */

/**
  * @}
  */

/**
  * @}
  */

/************************ (C) COPYRIGHT STMicroelectronics *****END OF FILE****/
