# 硬件版本变更日志 (Hardware Changelog)

## v2.0.0 (2026-07-27) — Rev2 双MCU架构
- **架构**: Dual MCU — STM32F407VET6 (Main/DQN) + STM32F103C8T6 (Aux/1kHz)
- **传感器**: VL53L1X (瓶身搜索 4m) + VL53L0X×4 (边缘检测) + MPU6050 IMU
- **通信**: HC-05 BLE + SPI桥接(Main↔Aux 100Hz) + RPi 40-pin GPIO
- **电机**: TB6612FNG 双路 → 编码器 L/R + TCRT5000×4 巡线
- **PCB**: 80×50mm 2层 FR4 1oz 铜厚
- **保护**: SS34 肖特基反向保护 + PTC 2A 自恢复保险丝

## v1.0.0 (2026-06) — Rev1 单MCU原型
- **架构**: STM32F103C8T6 单MCU
- **传感器**: VL53L0X×5 + MPU6050
- **电源**: MP1584 + AMS1117-3.3 (继承)
- **PCB**: 100×60mm 2层 FR4
