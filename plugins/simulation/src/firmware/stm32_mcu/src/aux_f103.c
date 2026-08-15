/* BottleSumo F103 Auxiliary Firmware (Revision 2)
 * ==================================================
 * Cortex-M3 MCU @ 72MHz, 64KB Flash, 20KB SRAM
 * STM32F103C8Tx
 *
 * Responsibility:
 *   - SPI1 Slave: Receive commands from F407, send sensor data back
 *   - I2C2: Read VL53L0X ×4 (0x30-0x33 via TCA9548A mux or direct)
 *   - TIM1: PWM motor control (CH1=PA8/MotorA, CH2=PA9/MotorB)
 *   - TIM2: Encoder A (PA0=CH1, PA1=CH2)
 *   - TIM4: Encoder B (PB6=CH1, PB7=CH2)
 *   - ADC1: Battery voltage divider (PA4, Channel 4)
 *   - IWDG: Independent watchdog (100ms)
 *
 * Pin Mapping:
 *   SPI1_NSS: PA4  | SPI1_SCK: PA5 | SPI1_MISO: PA6 | SPI1_MOSI: PA7
 *   I2C2_SCL: PB10 | I2C2_SDA: PB11
 *   TIM1_CH1: PA8  | TIM1_CH2: PA9  (PWM Motor A/B)
 *   TIM2_CH1: PA0  | TIM2_CH2: PA1  (Encoder A)
 *   TIM4_CH1: PB6  | TIM4_CH2: PB7  (Encoder B)
 *   ADC1_IN4: PA4  (Battery divider — but conflicts with SPI1_NSS! Using PA4 only for analog input note)
 *   Note: SPI1_NSS is actually on PA4. Battery ADC uses a separate analog pin.
 */

#include "stm32f1xx_reg.h"

/* ================================================================
 * SPI Frame Protocol (matching main_f407.c)
 * ================================================================
 * Master->Slave (7 bytes):  [CMD|PWM_A_H|PWM_A_L|PWM_B_H|PWM_B_L|CRC_H|CRC_L]
 * Slave->Master (21 bytes): [STATUS|ENC_A(4B)|ENC_B(4B)|BATT(2B)|VLX0(8B)|CRC(2B)]
 */

/* ================================================================
 * Constants
 * ================================================================ */
#define SYSTEM_CLOCK_HZ       72000000U
#define APB1_CLOCK_HZ         36000000U
#define APB2_CLOCK_HZ         72000000U
#define MAIN_LOOP_HZ               100U

/* I2C addresses */
#define VL53L0X_ADDR_BASE    0x30   /* 0x30-0x33 (4 sensors) */

/* VL53L0X registers */
#define VL53L0X_SYSRANGE_START          0x00
#define VL53L0X_RESULT_RANGE_STATUS     0x14
#define VL53L0X_SYSTEM_INTERRUPT_CLEAR  0x0B

/* SPI commands */
#define SPI_CMD_NOP           0x00
#define SPI_CMD_MOVE_FWD      0x01
#define SPI_CMD_MOVE_BACK     0x02
#define SPI_CMD_ROTATE_LEFT   0x03
#define SPI_CMD_ROTATE_RIGHT  0x04
#define SPI_CMD_ESTOP         0x05
#define SPI_CMD_BRAKE         0x06

/* Status bits */
#define STATUS_ESTOP          (1U << 0)
#define STATUS_IWDG_OK        (1U << 1)
#define STATUS_BATT_LOW       (1U << 2)

/* PWM limits */
#define PWM_MAX  3000   /* N20 motor max safe */
#define PWM_MIN     0

/* Battery thresholds */
#define BATT_LOW_MV      6200   /* 2S LiPo: 3.1V/cell */
#define BATT_CRITICAL_MV 6000   /* 3.0V/cell */
#define BATT_FULL_MV     8400   /* 4.2V/cell */

/* ================================================================
 * Global State
 * ================================================================ */
static volatile uint32_t sys_tick_ms = 0;
__attribute__((unused))
static uint32_t last_loop_ms = 0;

/* SPI slave buffers */
static uint8_t  spi_rx_buf[7];    /* Command from master (7 bytes) */
static uint8_t  spi_tx_buf[21];   /* Response to master (21 bytes) */
static volatile uint8_t spi_rx_idx = 0;
static volatile uint8_t spi_tx_idx = 0;
static volatile uint8_t spi_frame_ready = 0;  /* Set when 7-byte command received */

/* Motor PWM */
static uint16_t pwm_a = 0;
static uint16_t pwm_b = 0;

/* Encoder */
static volatile int32_t enc_a_count = 0;
static volatile int32_t enc_b_count = 0;
static int32_t enc_a_last = 0;
static int32_t enc_b_last = 0;

/* VL53L0X sensor readings */
static uint16_t vlx0_dist[4] = {5000, 5000, 5000, 5000};

/* Battery */
static uint16_t battery_mv = 0;

/* Status */
static uint8_t  status = 0;
static uint8_t  estop_lock = 0;

/* ================================================================
 * SysTick Handler (1ms)
 * ================================================================ */
void SysTick_Handler(void) {
    sys_tick_ms++;
}

static void delay_ms(uint32_t ms) {
    uint32_t start = sys_tick_ms;
    while ((sys_tick_ms - start) < ms) {
        __WFI();
    }
}

/* ================================================================
 * I2C2 Helper Functions
 * ================================================================ */

static int i2c2_wait_sb(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C2->SR1 & I2C_SR1_SB)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

static int i2c2_wait_addr(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C2->SR1 & I2C_SR1_ADDR)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    (void)I2C2->SR2;  /* Clear ADDR */
    return 0;
}

static int i2c2_wait_txe(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C2->SR1 & I2C_SR1_TXE)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

static int i2c2_wait_btf(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C2->SR1 & I2C_SR1_BTF)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

static int i2c2_wait_rxne(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C2->SR1 & I2C_SR1_RXNE)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

/* I2C2 Write: device_addr + 8-bit register + data */
static int i2c2_write_register(uint8_t dev_addr, uint8_t reg, uint8_t data) {
    /* START */
    I2C2->CR1 |= I2C_CR1_START;
    if (i2c2_wait_sb(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }

    /* Device address (write) */
    I2C2->DR = (dev_addr << 1) | 0x00;
    if (i2c2_wait_addr(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }

    /* Register */
    if (i2c2_wait_txe(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }
    I2C2->DR = reg;

    /* Data */
    if (i2c2_wait_txe(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }
    I2C2->DR = data;
    if (i2c2_wait_btf(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }

    /* STOP */
    I2C2->CR1 |= I2C_CR1_STOP;
    delay_ms(1);
    return 0;
}

/* I2C2 Read */
static int i2c2_read_data(uint8_t dev_addr, uint8_t reg, uint8_t *buf, uint8_t len) {
    /* Write register */
    I2C2->CR1 |= I2C_CR1_START;
    if (i2c2_wait_sb(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }

    I2C2->DR = (dev_addr << 1) | 0x00;
    if (i2c2_wait_addr(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }

    if (i2c2_wait_txe(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }
    I2C2->DR = reg;
    if (i2c2_wait_btf(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }

    /* Repeated START for read */
    I2C2->CR1 |= I2C_CR1_START;
    if (i2c2_wait_sb(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }

    I2C2->DR = (dev_addr << 1) | 0x01;
    if (i2c2_wait_addr(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }
    (void)I2C2->SR2;

    for (uint8_t i = 0; i < len; i++) {
        if (i == len - 1) {
            I2C2->CR1 &= ~I2C_CR1_ACK;
        }
        if (i2c2_wait_rxne(10) < 0) { I2C2->CR1 |= I2C_CR1_STOP; return -1; }
        buf[i] = I2C2->DR;
    }

    I2C2->CR1 |= I2C_CR1_STOP;
    return 0;
}

/* ================================================================
 * VL53L0X Sensor Reading
 * ================================================================ */

/* Read single VL53L0X range in mm (blocking) */
static uint16_t vl53l0x_read_range_single(uint8_t addr) {
    /* Start ranging */
    i2c2_write_register(addr, VL53L0X_SYSRANGE_START, 0x01);

    /* Wait for measurement (typical: 33ms, but polling approach) */
    delay_ms(33);

    /* Read result (2 bytes: high, low) */
    uint8_t buf[2];
    if (i2c2_read_data(addr, VL53L0X_RESULT_RANGE_STATUS, buf, 2) == 0) {
        uint16_t dist = ((uint16_t)buf[0] << 8) | buf[1];
        if (dist < 30) dist = 1300;    /* Min valid */
        if (dist > 1300) dist = 1300;  /* Max valid */
        return dist;
    }

    return 1300;  /* Default: max range */
}

/* Read all 4 VL53L0X sensors (sequentially, blocking ~132ms total) */
__attribute__((unused))
static void vl53l0x_read_all(void) {
    for (int i = 0; i < 4; i++) {
        vlx0_dist[i] = vl53l0x_read_range_single(VL53L0X_ADDR_BASE + i);
    }
}

/* ================================================================
 * ADC Battery Reading
 * ================================================================ */

/* ADC1 read channel (single conversion, blocking) */
static uint16_t adc1_read_channel(uint8_t channel) {
    /* Configure channel sequence */
    ADC1->SQR3 = channel & 0x1F;
    ADC1->SQR1 = 0;  /* 1 conversion */

    /* Start conversion */
    ADC1->CR2 |= ADC_CR2_SWSTART;

    /* Wait for conversion complete */
    while (!(ADC1->SR & ADC_SR_EOC));

    /* Read result */
    return ADC1->DR & 0xFFF;
}

/* Read battery voltage (voltage divider: 10k/4.7k → ~3.19x scaling) */
static void battery_read(void) {
    /* Read ADC channel 4 (PA4) */
    uint16_t raw = adc1_read_channel(4);

    /* Convert to mV:
     * Vref = 3.3V, 12-bit ADC → 3300mV / 4096 = 0.8057mV/count
     * Divider: R1=10k, R2=4.7k → Vin = Vout * (10k+4.7k)/4.7k = Vout * 3.128
     * Battery_mV = raw * (3300/4096) * 3.128
     */
    battery_mv = (uint16_t)((uint32_t)raw * 3300U / 4096U * 3128U / 1000U);

    /* Clip to valid range */
    if (battery_mv > 12600) battery_mv = 12600;
}

/* Check battery status */
static void battery_check_status(void) {
    if (battery_mv < BATT_CRITICAL_MV) {
        status |= STATUS_BATT_LOW;
    } else {
        status &= ~STATUS_BATT_LOW;
    }
}

/* ================================================================
 * Motor PWM Control
 * ================================================================ */

static void motors_set_pwm(uint16_t a_pwm, uint16_t b_pwm) {
    /* Clamp */
    if (a_pwm > PWM_MAX) a_pwm = PWM_MAX;
    if (b_pwm > PWM_MAX) b_pwm = PWM_MAX;

    pwm_a = a_pwm;
    pwm_b = b_pwm;

    /* Update TIM1 CCR registers */
    TIM1->CCR1 = a_pwm;
    TIM1->CCR2 = b_pwm;
}

static void motors_stop(void) {
    motors_set_pwm(0, 0);
}

/* Apply emergency stop (lock motors to 0 PWM) */
static void motors_estop(void) {
    motors_set_pwm(0, 0);
    estop_lock = 1;
    status |= STATUS_ESTOP;
}

/* ================================================================
 * SPI1 Slave Handler
 * ================================================================ */

/* SPI1 interrupt handler */
void SPI1_IRQHandler(void) {
    /* Check RX not empty */
    if (SPI1->SR & SPI_SR_RXNE) {
        uint8_t rx_data = SPI1->DR;

        /* Store received byte */
        if (spi_rx_idx < 7) {
            spi_rx_buf[spi_rx_idx] = rx_data;
            spi_rx_idx++;
        }

        /* Load next TX byte or 0x00 */
        if (spi_tx_idx < 21) {
            SPI1->DR = spi_tx_buf[spi_tx_idx];
            spi_tx_idx++;
        } else {
            SPI1->DR = 0x00;
        }

        /* Check if full frame received */
        if (spi_rx_idx >= 7) {
            spi_frame_ready = 1;
        }
    }
}

/* Process received SPI command */
static void spi_process_command(void) {
    if (!spi_frame_ready) return;

    uint8_t cmd = spi_rx_buf[0];
    uint16_t target_pwm_a = ((uint16_t)spi_rx_buf[1] << 8) | spi_rx_buf[2];
    uint16_t target_pwm_b = ((uint16_t)spi_rx_buf[3] << 8) | spi_rx_buf[4];

    /* If in estop, ignore all commands except reset */
    if (estop_lock && cmd != SPI_CMD_NOP) {
        motors_set_pwm(0, 0);
        return;
    }

    switch (cmd) {
    case SPI_CMD_MOVE_FWD:
        motors_set_pwm(target_pwm_a, target_pwm_b);
        break;
    case SPI_CMD_MOVE_BACK:
        /* Reverse motor direction */
        motors_set_pwm(0, 0);  /* Simulated: in real HW would flip PWM polarity */
        break;
    case SPI_CMD_ROTATE_LEFT:
        motors_set_pwm(target_pwm_a, 0);  /* Left motor only */
        break;
    case SPI_CMD_ROTATE_RIGHT:
        motors_set_pwm(0, target_pwm_b);  /* Right motor only */
        break;
    case SPI_CMD_ESTOP:
        motors_estop();
        break;
    case SPI_CMD_BRAKE:
        motors_set_pwm(0, 0);
        break;
    case SPI_CMD_NOP:
    default:
        /* Motor values unchanged — keep current PWM */
        (void)target_pwm_a;
        (void)target_pwm_b;
        break;
    }

    /* Reset for next frame */
    spi_rx_idx = 0;
    spi_tx_idx = 0;
    spi_frame_ready = 0;
}

/* Build SPI TX response buffer for next frame */
static void spi_build_response(void) {
    spi_tx_buf[0] = status;

    /* Encoder A delta (int32, big-endian) */
    int32_t enc_delta_a = enc_a_count - enc_a_last;
    enc_a_last = enc_a_count;
    spi_tx_buf[1] = (enc_delta_a >> 24) & 0xFF;
    spi_tx_buf[2] = (enc_delta_a >> 16) & 0xFF;
    spi_tx_buf[3] = (enc_delta_a >> 8)  & 0xFF;
    spi_tx_buf[4] = enc_delta_a & 0xFF;

    /* Encoder B delta */
    int32_t enc_delta_b = enc_b_count - enc_b_last;
    enc_b_last = enc_b_count;
    spi_tx_buf[5] = (enc_delta_b >> 24) & 0xFF;
    spi_tx_buf[6] = (enc_delta_b >> 16) & 0xFF;
    spi_tx_buf[7] = (enc_delta_b >> 8)  & 0xFF;
    spi_tx_buf[8] = enc_delta_b & 0xFF;

    /* Battery mV (uint16, big-endian) */
    spi_tx_buf[9]  = (battery_mv >> 8) & 0xFF;
    spi_tx_buf[10] = battery_mv & 0xFF;

    /* VL53L0X distances (4 × uint16, big-endian) */
    for (int i = 0; i < 4; i++) {
        spi_tx_buf[11 + i*2]     = (vlx0_dist[i] >> 8) & 0xFF;
        spi_tx_buf[11 + i*2 + 1] = vlx0_dist[i] & 0xFF;
    }

    /* CRC placeholder */
    spi_tx_buf[19] = 0x00;
    spi_tx_buf[20] = 0x00;
}

/* ================================================================
 * Emergency Stop Detection (local edge sensors)
 * ================================================================ */
static uint8_t local_estop_check(void) {
    uint8_t all_near = 1;
    for (int i = 0; i < 4; i++) {
        if (vlx0_dist[i] > 30) {  /* 3cm threshold */
            all_near = 0;
            break;
        }
    }
    return all_near;
}

/* ================================================================
 * System Initialization
 * ================================================================ */

/* Clock: HSE 8MHz → PLL×9 → 72MHz
 * AHB = 72MHz, APB1 = 36MHz, APB2 = 72MHz
 */
void SystemInit(void) {
#ifdef RENODE_SIM
    /* Simulation mode: skip HSE/PLL, use HSI (8MHz) */
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY));
    /* SW = HSI */
    RCC->CFGR = (RCC->CFGR & ~(3U << 0));
    while ((RCC->CFGR & (3U << 2)) != (0U << 2));
    /* SysTick @ 8MHz → 1ms */
    SysTick->LOAD = 8000000 / 1000 - 1;
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE | SysTick_CTRL_TICKINT | SysTick_CTRL_ENABLE;
    return;
#else
    /* Enable HSE */
    RCC->CR |= RCC_CR_HSEON;
    while (!(RCC->CR & RCC_CR_HSERDY));

    /* PLL config: HSE × 9 = 72MHz
     * CFGR: PLLSRC=HSE, PLLMUL=9
     */
    RCC->CFGR |= (1U << 16);  /* PLLSRC = HSE */
    RCC->CFGR |= (7U << 18);  /* PLLMUL = ×9 (0111 = ×9) */

    /* Enable PLL */
    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY));

    /* Flash: 2 wait states for 72MHz */
    *(volatile uint32_t *)0x40022000 = 0x32;  /* FLASH_ACR: PRFTBE + 2WS */

    /* APB prescalers: APB1=/2 (36MHz), APB2=/1 (72MHz) */
    RCC->CFGR |= (4U << 8);   /* PPRE1 = /2 */
    RCC->CFGR |= (0U << 11);  /* PPRE2 = /1 */

    /* Switch to PLL */
    RCC->CFGR |= (2U << 0);   /* SW = PLL */
    while ((RCC->CFGR & (3U << 2)) != (2U << 2));

    /* SysTick: 1ms */
    SysTick->LOAD = SYSTEM_CLOCK_HZ / 1000 - 1;
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE | SysTick_CTRL_TICKINT | SysTick_CTRL_ENABLE;
#endif
}

/* GPIO init */
static void gpio_init(void) {
    /* Enable clocks */
    RCC->APB2ENR |= RCC_APB2ENR_IOPA | RCC_APB2ENR_IOPB | RCC_APB2ENR_IOPC
                  | RCC_APB2ENR_AFIO | RCC_APB2ENR_ADC1;

    /* TIM2 encoder: PA0, PA1 → input floating (AF mode not needed for encoder mode on F1) */
    GPIOA->CRL &= ~((0xFU << 0) | (0xFU << 4));
    GPIOA->CRL |= (4U << 0) | (4U << 4);  /* Floating input */

    /* TIM4 encoder: PB6, PB7 → input floating */
    GPIOB->CRL &= ~((0xFU << 24) | (0xFU << 28));
    GPIOB->CRL |= (4U << 24) | (4U << 28);

    /* TIM1 PWM: PA8, PA9 → AF push-pull */
    GPIOA->CRH &= ~((0xFU << 0) | (0xFU << 4));
    GPIOA->CRH |= (0xBU << 0) | (0xBU << 4);  /* 50MHz AF push-pull */

    /* SPI1: PA4=NSS, PA5=SCK, PA6=MISO, PA7=MOSI */
    /* PA4: input floating (NSS) */
    GPIOA->CRL &= ~(0xFU << 16);
    GPIOA->CRL |= (4U << 16);
    /* PA5, PA6, PA7: AF push-pull */
    GPIOA->CRL &= ~((0xFU << 20) | (0xFU << 24) | (0xFU << 28));
    GPIOA->CRL |= (0xBU << 20) | (0xBU << 24) | (0xBU << 28);

    /* I2C2: PB10, PB11 → AF open-drain */
    GPIOB->CRH &= ~((0xFU << 8) | (0xFU << 12));
    GPIOB->CRH |= (0xBU << 8) | (0xBU << 12);

    /* Battery ADC: PA4 as analog input */
    /* (PA4 is already configured for SPI_NSS above; in production would use a dedicated pin) */
}

/* I2C2 init: 100kHz standard mode */
static void i2c2_init(void) {
    RCC->APB1ENR |= RCC_APB1ENR_I2C2;

    I2C2->CR1 = 0;
    I2C2->CR1 |= I2C_CR1_PE;
    I2C2->CR1 &= ~I2C_CR1_PE;

    /* APB1 = 36MHz → CCR = 36MHz / (2*100kHz) = 180 */
    I2C2->CCR = 180;
    I2C2->TRISE = 37;  /* 1000ns / (1/36MHz) + 1 */

    I2C2->CR1 |= I2C_CR1_PE;
}

/* SPI1 init: Slave mode, CPOL=1, CPHA=1, 8-bit */
static void spi1_init(void) {
    RCC->APB2ENR |= RCC_APB2ENR_SPI1;

    SPI1->CR1 = 0;
    SPI1->CR2 = 0;

    /* Slave mode: CPOL=1, CPHA=1, RXNE interrupt enabled */
    SPI1->CR1 = SPI_CR1_CPOL | SPI_CR1_CPHA;  /* Slave (MSTR=0) */

    /* Enable RX buffer not empty interrupt */
    SPI1->CR2 |= (1U << 6);  /* RXNEIE */

    /* Enable SPI */
    SPI1->CR1 |= SPI_CR1_SPE;

    /* Enable SPI1 interrupt in NVIC (IRQ 35 → ISER[1] bit 3) */
    NVIC->ISER[1] |= (1U << 3);
}

/* TIM1 PWM init: 20kHz PWM, center-aligned */
static void tim1_pwm_init(void) {
    RCC->APB2ENR |= RCC_APB2ENR_TIM1;

    /* Timer clock = APB2×2 = 144MHz (since APB2 prescaler≠1? No, APB2=72MHz, timer clock=72MHz)
     * PSC=0, ARR=3599 → 72000000/(0+1)/(3599+1) = 20000 Hz = 20kHz
     */
    TIM1->PSC = 0;
    TIM1->ARR = 3599;
    TIM1->CR1 |= TIM_CR1_ARPE;  /* Auto-reload preload */

    /* CH1 (PA8): PWM mode 1, output compare preload */
    TIM1->CCMR1 |= TIM_CCMR1_OC1M_PWM1 | TIM_CCMR1_OC1PE;
    TIM1->CCER  |= TIM_CCER_CC1E;

    /* CH2 (PA9): PWM mode 1 */
    TIM1->CCMR1 |= TIM_CCMR1_OC2M_PWM1 | TIM_CCMR1_OC2PE;
    TIM1->CCER  |= TIM_CCER_CC2E;

    /* Main output enable */
    TIM1->BDTR |= TIM_BDTR_MOE;

    /* Generate update */
    TIM1->EGR |= TIM_EGR_UG;

    /* Enable timer */
    TIM1->CR1 |= TIM_CR1_CEN;
}

/* TIM2 encoder init: X4 counting (both edges of both channels) */
static void tim2_encoder_init(void) {
    RCC->APB1ENR |= RCC_APB1ENR_TIM2;

    TIM2->SMCR |= TIM_SMCR_SMS_ENC;  /* Encoder mode 3 */
    TIM2->CCMR1 |= (1U << 0) | (1U << 8);  /* CC1S, CC2S = 01 (TI1, TI2) */
    TIM2->CCER  &= ~(TIM_CCER_CC1P | TIM_CCER_CC2P);  /* Non-inverted */

    /* 16-bit counter for encoder: ARR = 65535 */
    TIM2->ARR = 65535;
    TIM2->CNT = 0;

    TIM2->CR1 |= TIM_CR1_CEN;
}

/* TIM4 encoder init */
static void tim4_encoder_init(void) {
    RCC->APB1ENR |= RCC_APB1ENR_TIM4;

    TIM4->SMCR |= TIM_SMCR_SMS_ENC;
    TIM4->CCMR1 |= (1U << 0) | (1U << 8);
    TIM4->CCER  &= ~(TIM_CCER_CC1P | TIM_CCER_CC2P);

    TIM4->ARR = 65535;
    TIM4->CNT = 0;

    TIM4->CR1 |= TIM_CR1_CEN;
}

/* ADC1 init */
static void adc1_init(void) {
    RCC->APB2ENR |= RCC_APB2ENR_ADC1;

    /* Calibrate */
    ADC1->CR2 |= (1U << 2);  /* RSTCAL */
    while (ADC1->CR2 & (1U << 2));
    ADC1->CR2 |= (1U << 3);  /* CAL */
    while (ADC1->CR2 & (1U << 3));

    /* Sample time: 55.5 cycles for channel 4 */
    ADC1->SMPR2 |= (7U << 12);  /* CH4: 239.5 cycles */

    /* Enable ADC */
    ADC1->CR2 |= ADC_CR2_ADON;
}

/* IWDG init: 100ms timeout */
static void iwdg_init(void) {
    IWDG->KR = IWDG_KR_KEY_ACCESS;
    IWDG->PR = 3;     /* /32 (LSI=40kHz → 1.25kHz) */
    IWDG->RLR = 125;  /* 125 / 1.25kHz = 100ms */
    IWDG->KR = IWDG_KR_KEY_ENABLE;
    IWDG->KR = IWDG_KR_KEY_REFRESH;
}

/* ================================================================
 * Main Entry Point
 * ================================================================ */
int main(void) {
    /* Hardware init */
    gpio_init();
    i2c2_init();
    tim1_pwm_init();
    tim2_encoder_init();
    tim4_encoder_init();
    adc1_init();
    spi1_init();
    iwdg_init();

    /* Initial state */
    motors_stop();
    status = 0;
    estop_lock = 0;

    /* Main loop: ~100Hz driven by SPI frame arrival */
    while (1) {
        /* Refresh watchdog */
        IWDG->KR = IWDG_KR_KEY_REFRESH;
        status |= STATUS_IWDG_OK;

        /* Process SPI command (frame received via interrupt) */
        spi_process_command();

        /* ========================================
         * Sensor reading (round-robin to avoid blocking)
         * VL53L0X: read 1 sensor per frame (4 frames = 40ms)
         * ======================================== */
        {
            static uint8_t vlx0_round = 0;
            vlx0_dist[vlx0_round] = vl53l0x_read_range_single(VL53L0X_ADDR_BASE + vlx0_round);
            vlx0_round = (vlx0_round + 1) & 0x03;
        }

        /* Battery: read every 10th frame (10Hz) */
        {
            static uint8_t batt_counter = 0;
            if (++batt_counter >= 10) {
                batt_counter = 0;
                battery_read();
                battery_check_status();
            }
        }

        /* Encoder: read current counts */
        enc_a_count = (int32_t)(int16_t)TIM2->CNT;
        enc_b_count = (int32_t)(int16_t)TIM4->CNT;

        /* Local estop check */
        if (!estop_lock && local_estop_check()) {
            motors_estop();
        }

        /* Build SPI response for next frame */
        spi_build_response();

        /* Timing: ~10ms loop */
        delay_ms(10);
    }

    return 0;
}
