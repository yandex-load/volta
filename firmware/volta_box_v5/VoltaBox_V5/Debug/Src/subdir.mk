################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Src/bsp_driver_sd.c \
../Src/buffer.c \
../Src/fatfs.c \
../Src/main.c \
../Src/stm32f1xx_hal_msp.c \
../Src/stm32f1xx_it.c \
../Src/system_stm32f1xx.c \
../Src/usb_device.c \
../Src/usbd_cdc_if.c \
../Src/usbd_conf.c \
../Src/usbd_desc.c 

OBJS += \
./Src/bsp_driver_sd.o \
./Src/buffer.o \
./Src/fatfs.o \
./Src/main.o \
./Src/stm32f1xx_hal_msp.o \
./Src/stm32f1xx_it.o \
./Src/system_stm32f1xx.o \
./Src/usb_device.o \
./Src/usbd_cdc_if.o \
./Src/usbd_conf.o \
./Src/usbd_desc.o 

C_DEPS += \
./Src/bsp_driver_sd.d \
./Src/buffer.d \
./Src/fatfs.d \
./Src/main.d \
./Src/stm32f1xx_hal_msp.d \
./Src/stm32f1xx_it.d \
./Src/system_stm32f1xx.d \
./Src/usb_device.d \
./Src/usbd_cdc_if.d \
./Src/usbd_conf.d \
./Src/usbd_desc.d 


# Each subdirectory must supply rules for building sources it contributes
Src/%.o: ../Src/%.c
	@echo 'Building file: $<'
	@echo 'Invoking: MCU GCC Compiler'
	@echo $(PWD)
	arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -mfloat-abi=soft '-D__weak=__attribute__((weak))' '-D__packed="__attribute__((__packed__))"' -DUSE_HAL_DRIVER -DSTM32F103xE -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Inc" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Drivers/STM32F1xx_HAL_Driver/Inc" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Drivers/STM32F1xx_HAL_Driver/Inc/Legacy" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Middlewares/ST/STM32_USB_Device_Library/Core/Inc" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Drivers/CMSIS/Device/ST/STM32F1xx/Include" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Drivers/CMSIS/Include" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Middlewares/Third_Party/FatFs/src/drivers" -I"/home/slavik763/STM32_workspace/VoltaBox_V5/Middlewares/Third_Party/FatFs/src"  -O3 -g3 -Wall -fmessage-length=0 -ffunction-sections -c -fmessage-length=0 -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '


