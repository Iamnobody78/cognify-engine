/**
 * BottleSumo SPI Protocol — Shared Header
 * ========================================
 * Defines the inter-MCU communication protocol between
 *   STM32F407VET6 (MAIN, SPI Master) and STM32F103C8T6 (AUX, SPI Slave)
 *
 * Extracted from: main_f407.c + aux_f103.c (2026-07-30)
 * Author: AionRS Governance Agent
 */

#ifndef BOTTLESUMO_SPI_PROTOCOL_H_
#define BOTTLESUMO_SPI_PROTOCOL_H_

/* ================================================================
 * Physical Layer
 * ================================================================
 * Bus:        SPI1 (F103 Slave) ←→ SPI2 (F407 Master)
 * Clock:      10MHz (APB2/8 prescaler)
 * Mode:       0 (CPOL=0, CPHA=0)
 * Data:       8-bit frames, MSB first
 * NSS:        Hardware (PA4 on F103)
 * ----------------------------------
 * F103 Pin Map:
 *   SPI1_NSS: PA4  | SPI1_SCK: PA5 | SPI1_MISO: PA6 | SPI1_MOSI: PA7
 * F407 Pin Map:
 *   SPI2 pins (board-specific)
 */

#define SPI_CLOCK_HZ    10000000U   /* 10 MHz */
#define SPI_PRESCALER   8U          /* APB2 ÷ 8 */

/* ================================================================
 * Frame Sizes
 * ================================================================ */
#define MASTER_TO_SLAVE_FRAME_SIZE  7U   /* [CMD(1)|PWM_A(2)|PWM_B(2)|CRC(2)] */
#define SLAVE_TO_MASTER_FRAME_SIZE  21U  /* [STATUS(1)|ENC_A(4)|ENC_B(4)|BATT(2)|VLX0(8)|CRC(2)] */

/* ================================================================
 * Master → Slave Commands (byte 0)
 * ================================================================ */
#define SPI_CMD_NOP           0x00  /* No operation */
#define SPI_CMD_MOVE_FWD      0x01  /* Move forward (PWM_A, PWM_B > 0) */
#define SPI_CMD_MOVE_BACK     0x02  /* Move backward */
#define SPI_CMD_ROTATE_LEFT   0x03  /* Rotate counter-clockwise */
#define SPI_CMD_ROTATE_RIGHT  0x04  /* Rotate clockwise */
#define SPI_CMD_ESTOP         0x05  /* Emergency stop (disable motors, enter safe state) */
#define SPI_CMD_BRAKE         0x06  /* Active braking (short motor windings) */
/* Reserved: 0x07–0xFF */

/* ================================================================
 * Master → Slave PWM Payload (bytes 1–4)
 * ================================================================ */
/* PWM_A: bytes 1 (H), 2 (L) — Motor A (left) duty cycle */
/* PWM_B: bytes 3 (H), 4 (L) — Motor B (right) duty cycle */
/* Valid range: 0–3000 (N20 micro metal gearmotor safe limit) */

/* ================================================================
 * Slave → Master Status Bits (byte 0 of response)
 * ================================================================ */
#define STATUS_ESTOP          (1U << 0)  /* Emergency stop active (edge sensor triggered) */
#define STATUS_IWDG_OK        (1U << 1)  /* Independent watchdog healthy */
#define STATUS_BATT_LOW       (1U << 2)  /* Battery voltage below 6.2V (3.1V/cell) */
/* Reserved: bits 3–7 */

/* ================================================================
 * Slave → Master Sensor Payload (bytes 1–20)
 * ================================================================ */
/* Encoder A (bytes 1–4): int32_t, encoder counts (TIM2) */
/* Encoder B (bytes 5–8): int32_t, encoder counts (TIM4) */
/* Battery   (bytes 9–10): uint16_t, mV (e.g., 7400 = 7.4V) */
/* VL53L0X   (bytes 11–18): uint16_t ×4, mm (sensor 0–3, 0x30–0x33) */
/* CRC8      (bytes 5–6 of command, bytes 19–20 of response) */

/* ================================================================
 * CRC-8 (Dallas/Maxim)
 * ================================================================
 * Polynomial: 0x31 (x^8 + x^5 + x^4 + 1)
 * Initial:    0x00
 * Reflect In: true
 * Reflect Out: true
 * Xor Out:    0x00
 * TODO: Implement CRC-8 calculation in shared crc8.c
 *
 * static uint8_t crc8(const uint8_t *data, size_t len);
 */

/* ================================================================
 * Battery Thresholds
 * ================================================================ */
#define BATT_LOW_MV          6200U  /* 2S LiPo: 3.1V/cell — warning */
#define BATT_CRITICAL_MV     6000U  /* 3.0V/cell — forced stop */
#define BATT_FULL_MV         8400U  /* 4.2V/cell — fully charged */

/* ================================================================
 * PWM Limits
 * ================================================================ */
#define PWM_MAX              3000   /* N20 motor maximum safe duty */
#define PWM_MIN              0

#endif /* BOTTLESUMO_SPI_PROTOCOL_H_ */
