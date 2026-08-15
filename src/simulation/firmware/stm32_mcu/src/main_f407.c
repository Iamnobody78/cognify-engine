/* BottleSumo F407 Main Firmware (Revision 2)
 * ============================================
 * Cortex-M4 MCU @ 168MHz, 1024KB Flash, 192KB SRAM
 * STM32F407VGTx
 *
 * Responsibility:
 *   - DQN inference for autonomous decision-making
 *   - I2C1: Read VL53L1X (0x29) + MPU6050 (0x68)
 *   - SPI2 Master: Command/reply with F103 aux MCU
 *   - USART3: BLE telemetry output (115200)
 *   - IWDG: Independent watchdog (100ms)
 *   - State machine: IDLE→SEARCH→APPROACH→ATTACK→RECOVER
 *
 * Pin Mapping:
 *   I2C1_SCL: PB6   | I2C1_SDA: PB7
 *   SPI2_SCK: PB13  | SPI2_MISO: PB14 | SPI2_MOSI: PB15 | SPI2_NSS: PB12
 *   USART3_TX: PB10 | USART3_RX: PB11
 */

#include "stm32f4xx_reg.h"
#include "dqn_weights.h"

/* ================================================================
 * SPI Frame Protocol (100Hz)
 * ================================================================
 * Master->Slave (7 bytes):
 *   [0]    Command: 0x00=NOP, 0x01=MOVE_FWD, 0x02=IDLE, 0x03=ESTOP
 *   [1:2]  Motor A PWM (uint16, 0-4095) - left
 *   [3:4]  Motor B PWM (uint16, 0-4095) - right
 *   [5:6]  CRC16
 *
 * Slave->Master (21 bytes):
 *   [0]    Status: bit0=ESTOP, bit1=IWDG_OK, bit2=BATT_LOW
 *   [1:4]  Encoder A delta (int32, ticks since last frame)
 *   [5:8]  Encoder B delta (int32)
 *   [9:10] Battery mV (uint16)
 *   [11:12] VLX0_0 distance mm (uint16)  // Front-left
 *   [13:14] VLX0_1 distance mm (uint16)  // Front-right
 *   [15:16] VLX0_2 distance mm (uint16)  // Back-left
 *   [17:18] VLX0_3 distance mm (uint16)  // Back-right
 *   [19:20] CRC16
 */

/* ================================================================
 * Constants
 * ================================================================ */
#define SYSTEM_CLOCK_HZ      168000000U
#define APB1_CLOCK_HZ         42000000U
#define APB2_CLOCK_HZ         84000000U
#define MAIN_LOOP_HZ               100U
#define MAIN_LOOP_PERIOD_MS         10U

/* I2C addresses */
#define VL53L1X_ADDR        0x29
#define MPU6050_ADDR         0x68

/* VL53L1X registers */
#define VL53L1X_RESULT_RANGE_STATUS  0x0089
#define VL53L1X_RESULT_INTERRUPT     0x0086
#define VL53L1X_SYSTEM_MODE_START    0x0087

/* MPU6050 registers */
#define MPU6050_ACCEL_XOUT_H   0x3B
#define MPU6050_PWR_MGMT_1     0x6B
#define MPU6050_GYRO_CONFIG    0x1B
#define MPU6050_ACCEL_CONFIG   0x1C

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

/* State machine */
enum {
    STATE_IDLE = 0,
    STATE_SEARCH,
    STATE_APPROACH,
    STATE_ATTACK,
    STATE_RECOVER,
    STATE_ESTOP
};

/* Action indices (DQN output) */
#define ACTION_IDLE           0
#define ACTION_FWD            1
#define ACTION_BACK           2
#define ACTION_LEFT           3
#define ACTION_RIGHT          4
#define ACTION_FWD_LEFT       5
#define ACTION_FWD_RIGHT      6
#define ACTION_BACK_LEFT      7
#define ACTION_BACK_RIGHT     8
#define ACTION_ATTACK         9
#define ACTION_ESTOP          10

/* ================================================================
 * Global State
 * ================================================================ */
static volatile uint32_t sys_tick_ms = 0;
static uint8_t  robot_state = STATE_IDLE;
static uint8_t  prev_state = STATE_IDLE;
static uint32_t state_entry_ms = 0;
static uint32_t last_loop_ms = 0;
static uint32_t frame_count = 0;

/* Sensor data */
static uint16_t vl53l1x_dist_mm = 5000;  /* VL53L1X front distance */
static int16_t  mpu6050_accel_x = 0;
static int16_t  mpu6050_accel_y = 0;
static int16_t  mpu6050_accel_z = 0;
static int16_t  mpu6050_gyro_z  = 0;

/* SPI slave response */
static int32_t  enc_a_delta = 0;
static int32_t  enc_b_delta = 0;
static uint16_t battery_mv = 0;
static uint16_t vlx0_dist[4] = {5000, 5000, 5000, 5000};
static uint8_t  slave_status = 0;

/* Cylinder detection */
static uint16_t bottle_dist_history[3] = {5000, 5000, 5000};
static uint8_t  bottle_dist_idx = 0;
static uint8_t  cylinder_detected = 0;

/* DQN observation */
static float observation[OBS_DIM];

/* ================================================================
 * SysTick Handler
 * ================================================================ */
void SysTick_Handler(void) {
    sys_tick_ms++;
}

/* ================================================================
 * Delay (blocking, in ms)
 * ================================================================ */
static void delay_ms(uint32_t ms) {
    uint32_t start = sys_tick_ms;
    while ((sys_tick_ms - start) < ms) {
        __WFI();
    }
}

/* ================================================================
 * I2C Helper Functions
 * Renode handles the peripheral state; we use polling with timeout.
 * ================================================================ */
static int i2c1_wait_sb(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C1->SR1 & I2C_SR1_SB)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

static int i2c1_wait_addr(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C1->SR1 & I2C_SR1_ADDR)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    /* Clear ADDR by reading SR1 then SR2 */
    (void)I2C1->SR2;
    return 0;
}

static int i2c1_wait_txe(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C1->SR1 & I2C_SR1_TXE)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

static int i2c1_wait_btf(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C1->SR1 & I2C_SR1_BTF)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

static int i2c1_wait_rxne(uint32_t timeout_ms) {
    uint32_t start = sys_tick_ms;
    while (!(I2C1->SR1 & I2C_SR1_RXNE)) {
        if ((sys_tick_ms - start) > timeout_ms) return -1;
    }
    return 0;
}

/* I2C1 Write: addr + register + data */
static int i2c1_write_register(uint8_t dev_addr, uint16_t reg, uint8_t data) {
    uint16_t reg_high = (reg >> 8) & 0xFF;
    uint16_t reg_low = reg & 0xFF;

    /* Generate START */
    I2C1->CR1 |= I2C_CR1_START;
    if (i2c1_wait_sb(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }

    /* Send device address (write) */
    I2C1->DR = (dev_addr << 1) | 0x00;
    if (i2c1_wait_addr(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }

    /* Send register high byte */
    if (i2c1_wait_txe(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }
    I2C1->DR = reg_high;

    /* Send register low byte */
    if (i2c1_wait_txe(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }
    I2C1->DR = reg_low;

    /* Send data */
    if (i2c1_wait_txe(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }
    I2C1->DR = data;
    if (i2c1_wait_btf(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }

    /* STOP */
    I2C1->CR1 |= I2C_CR1_STOP;
    delay_ms(1);
    return 0;
}

/* I2C1 Write register address only (for repeated start reads) */
static int i2c1_write_reg_addr(uint8_t dev_addr, uint16_t reg) {
    I2C1->CR1 |= I2C_CR1_START;
    if (i2c1_wait_sb(10) < 0) return -1;

    I2C1->DR = (dev_addr << 1) | 0x00;
    if (i2c1_wait_addr(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }
    (void)I2C1->SR2;

    if (i2c1_wait_txe(10) < 0) return -1;
    I2C1->DR = (reg >> 8) & 0xFF;

    if (i2c1_wait_txe(10) < 0) return -1;
    I2C1->DR = reg & 0xFF;

    if (i2c1_wait_btf(10) < 0) return -1;
    return 0;
}

/* I2C1 Read multiple bytes */
static int i2c1_read_data(uint8_t dev_addr, uint16_t reg, uint8_t *buf, uint8_t len) {
    /* Write register address first */
    if (i2c1_write_reg_addr(dev_addr, reg) < 0) return -1;

    /* Repeated START for read */
    I2C1->CR1 |= I2C_CR1_START;
    if (i2c1_wait_sb(10) < 0) return -1;

    I2C1->DR = (dev_addr << 1) | 0x01;
    if (i2c1_wait_addr(10) < 0) { I2C1->CR1 |= I2C_CR1_STOP; return -1; }
    (void)I2C1->SR2;

    for (uint8_t i = 0; i < len; i++) {
        /* Enable ACK for all but last byte */
        if (i == len - 1) {
            I2C1->CR1 &= ~I2C_CR1_ACK;  /* NACK last byte */
        }
        if (i2c1_wait_rxne(10) < 0) return -1;
        buf[i] = I2C1->DR;
    }

    I2C1->CR1 |= I2C_CR1_STOP;
    return 0;
}

/* ================================================================
 * Sensor Drivers
 * ================================================================ */

/* Read VL53L1X distance in mm */
static uint16_t vl53l1x_read_range(void) {
    uint8_t buf[2];
    /* Write SYSRANGE_START */
    i2c1_write_register(VL53L1X_ADDR, VL53L1X_SYSTEM_MODE_START, 0x01);
    delay_ms(50);  /* Blocking 50ms (target: 20Hz, budget ~50ms) */

    /* Read RESULT_RANGE_STATUS (2 bytes) */
    if (i2c1_read_data(VL53L1X_ADDR, VL53L1X_RESULT_RANGE_STATUS, buf, 2) == 0) {
        uint16_t dist = ((uint16_t)buf[0] << 8) | buf[1];
        if (dist < 10) dist = 5000;    /* Min valid = 10mm */
        if (dist > 4000) dist = 4000;  /* Max valid = 4000mm */
        return dist;
    }
    return 5000;  /* Default: no reading */
}

/* Read MPU6050 accelerometer (raw 16-bit) */
static void mpu6050_read_accel(void) {
    uint8_t buf[6];
    if (i2c1_read_data(MPU6050_ADDR, MPU6050_ACCEL_XOUT_H, buf, 6) == 0) {
        mpu6050_accel_x = (int16_t)(((uint16_t)buf[0] << 8) | buf[1]);
        mpu6050_accel_y = (int16_t)(((uint16_t)buf[2] << 8) | buf[3]);
        mpu6050_accel_z = (int16_t)(((uint16_t)buf[4] << 8) | buf[5]);
    }
}

/* Initialize MPU6050 */
static void mpu6050_init(void) {
    /* Wake up from sleep (clear bit 6) */
    i2c1_write_register(MPU6050_ADDR, MPU6050_PWR_MGMT_1, 0x00);
    delay_ms(10);
    /* Accel: +/- 4g range */
    i2c1_write_register(MPU6050_ADDR, MPU6050_ACCEL_CONFIG, 0x08);
    /* Gyro: +/- 500 deg/s */
    i2c1_write_register(MPU6050_ADDR, MPU6050_GYRO_CONFIG, 0x08);
}

/* ================================================================
 * Cylinder Detection (3-frame convergence heuristic)
 * Review Item #6: False positive/negative reduction
 * ================================================================ */
static uint8_t detect_cylinder(uint16_t current_dist) {
    /* Update history ring buffer */
    bottle_dist_history[bottle_dist_idx] = current_dist;
    bottle_dist_idx = (bottle_dist_idx + 1) % 3;

    /* Check convergence: all 3 readings < 1m and max delta < 50mm */
    uint16_t d0 = bottle_dist_history[0];
    uint16_t d1 = bottle_dist_history[1];
    uint16_t d2 = bottle_dist_history[2];

    if (d0 >= 1000 || d1 >= 1000 || d2 >= 1000) return 0;

    uint16_t dmax = d0;
    uint16_t dmin = d0;
    if (d1 > dmax) dmax = d1;
	    if (d1 < dmin) dmin = d1;
    if (d2 > dmax) dmax = d2;
	    if (d2 < dmin) dmin = d2;

    return (dmax - dmin < 50) ? 1 : 0;
}

/* ================================================================
 * Emergency Stop Detection (4 edge sensors)
 * Review Item #5: Estop lock with manual reset
 * ================================================================ */
static uint8_t check_estop(void) {
    uint8_t all_near = 1;
    for (int i = 0; i < 4; i++) {
        if (vlx0_dist[i] > 30) {  /* All 4 edge sensors < 3cm */
            all_near = 0;
            break;
        }
    }
    return all_near;
}

/* ================================================================
 * SPI Master Communication
 * ================================================================ */

/* SPI2 send byte and receive response byte */
static uint8_t spi2_transfer_byte(uint8_t tx_data) {
    /* Wait for TXE */
    while (!(SPI2->SR & SPI_SR_TXE));
    SPI2->DR = tx_data;
    /* Wait for RXNE */
    while (!(SPI2->SR & SPI_SR_RXNE));
    return SPI2->DR;
}

/* SPI2 send command frame and receive response */
static void spi2_exchange_frame(void) {
    static uint8_t tx_buf[7];
    static uint8_t rx_buf[21];

    /* Build command frame */
    tx_buf[0] = 0;  /* Will be set by state machine */
    /* Motor PWM values set based on state */
    /* CRC placeholder for now */

    /* Chip select LOW (manual SS) */
    GPIOB->ODR &= ~(1U << 12);

    /* Send 7 bytes, receive 7 dummy bytes */
    for (int i = 0; i < 7; i++) {
        spi2_transfer_byte(tx_buf[i]);
    }

    /* Continue clocking to receive remaining 14 bytes */
    for (int i = 0; i < 14; i++) {
        rx_buf[i] = spi2_transfer_byte(0x00);
    }

    /* Chip select HIGH */
    GPIOB->ODR |= (1U << 12);

    /* Parse response */
    slave_status  = rx_buf[0];
    enc_a_delta   = ((int32_t)rx_buf[1] << 24) | ((int32_t)rx_buf[2] << 16)
                  | ((int32_t)rx_buf[3] << 8)  | rx_buf[4];
    enc_b_delta   = ((int32_t)rx_buf[5] << 24) | ((int32_t)rx_buf[6] << 16)
                  | ((int32_t)rx_buf[7] << 8)  | rx_buf[8];
    battery_mv    = ((uint16_t)rx_buf[9] << 8) | rx_buf[10];

    for (int i = 0; i < 4; i++) {
        vlx0_dist[i] = ((uint16_t)rx_buf[11 + i*2] << 8) | rx_buf[12 + i*2];
    }
}

/* ================================================================
 * DQN Inference
 * Uses shared weights from dqn_weights.c (16→128→64→11)
 * ================================================================ */

/* Build observation vector from sensor data */
static void build_observation(void) {
    /* OBS_DIM = 16 dimensions:
     * [0]   front_dist_mm / 4000.0f         (VL53L1X)
     * [1-4] edge_dist_mm[i] / 1300.0f       (VL53L0X x4)
     * [5]   accel_x / 32768.0f              (MPU6050)
     * [6]   accel_y / 32768.0f
     * [7]   accel_z / 32768.0f
     * [8]   gyro_z / 32768.0f
     * [9]   enc_a_delta / 100.0f            (normalized encoder)
     * [10]  enc_b_delta / 100.0f
     * [11]  battery_mv / 8400.0f
     * [12]  cylinder_detected
     * [13]  state_onehot[0]                  (STATE_IDLE)
     * [14]  state_onehot[1]                  (STATE_SEARCH)
     * [15]  state_onehot[2]                  (STATE_APPROACH)
     */
    observation[0]  = vl53l1x_dist_mm / 4000.0f;
    for (int i = 0; i < 4; i++) {
        observation[1 + i] = vlx0_dist[i] / 1300.0f;
    }
    observation[5]  = mpu6050_accel_x / 32768.0f;
    observation[6]  = mpu6050_accel_y / 32768.0f;
    observation[7]  = mpu6050_accel_z / 32768.0f;
    observation[8]  = mpu6050_gyro_z / 32768.0f;
    observation[9]  = enc_a_delta / 100.0f;
    observation[10] = enc_b_delta / 100.0f;
    observation[11] = battery_mv / 8400.0f;

    /* Cylinder detected flag */
    observation[12] = cylinder_detected ? 1.0f : 0.0f;

    /* State one-hot (simplified to 3 bits for observation) */
    observation[13] = (robot_state == STATE_IDLE) ? 1.0f : 0.0f;
    observation[14] = (robot_state == STATE_SEARCH) ? 1.0f : 0.0f;
    observation[15] = (robot_state == STATE_APPROACH || robot_state == STATE_ATTACK) ? 1.0f : 0.0f;
}

/* Select best action from Q-values (calls shared dqn_inference) */
static int select_action(void) {
    float q_values[NUM_ACTIONS];
    dqn_inference(observation, q_values);

    /* Argmax */
    int best_action = 0;
    float best_q = q_values[0];
    for (int i = 1; i < NUM_ACTIONS; i++) {
        if (q_values[i] > best_q) {
            best_q = q_values[i];
            best_action = i;
        }
    }
    return best_action;
}

/* ================================================================
 * State Machine
 * ================================================================ */
static void state_machine_update(void) {
    uint8_t new_state = robot_state;

    switch (robot_state) {
    case STATE_IDLE:
        /* Wait for start signal or transition to SEARCH */
        if (sys_tick_ms > 5000) {  /* Start after 5 seconds (competition start) */
            new_state = STATE_SEARCH;
        }
        break;

    case STATE_SEARCH:
        /* Rotate to find bottle. If cylinder detected → APPROACH */
        if (cylinder_detected && vl53l1x_dist_mm < 500) {
            new_state = STATE_APPROACH;
        }
        /* Timeout: 15 seconds without detection → stay searching */
        break;

    case STATE_APPROACH:
        /* Move toward bottle. If close enough (< 100mm) → ATTACK */
        if (vl53l1x_dist_mm < 100) {
            new_state = STATE_ATTACK;
        }
        /* Lost target? Go back to SEARCH */
        if (vl53l1x_dist_mm > 1000 || !cylinder_detected) {
            if ((sys_tick_ms - state_entry_ms) > 3000) {
                new_state = STATE_SEARCH;
            }
        }
        break;

    case STATE_ATTACK:
        /* Push bottle toward edge */
        /* If we stop or lose target, RECOVER */
        if (vl53l1x_dist_mm > 500 || !cylinder_detected) {
            new_state = STATE_RECOVER;
        }
        break;

    case STATE_RECOVER:
        /* Back up and re-search */
        if ((sys_tick_ms - state_entry_ms) > 2000) {
            new_state = STATE_SEARCH;
        }
        break;

    case STATE_ESTOP:
        /* Locked state - requires manual reset */
        break;
    }

    /* State transition */
    if (new_state != robot_state) {
        prev_state = robot_state;
        robot_state = new_state;
        state_entry_ms = sys_tick_ms;
    }
}

/* ================================================================
 * Motor Commands (translated to PWM via SPI)
 * ================================================================ */
static uint16_t motor_a_pwm = 0;
static uint16_t motor_b_pwm = 0;
static uint8_t  spi_cmd = SPI_CMD_NOP;

/* PWM range: 0=stop, 4095=max. Max safe: ~3000 for N20 motors */
#define PWM_MAX 3000
#define PWM_CRUISE 1500
#define PWM_TURN 1000

static void set_motors(uint16_t left_pwm, uint16_t right_pwm) {
    motor_a_pwm = left_pwm;
    motor_b_pwm = right_pwm;
}

static void execute_action(int action) {
    switch (action) {
    case ACTION_IDLE:
        spi_cmd = SPI_CMD_NOP;
        set_motors(0, 0);
        break;
    case ACTION_FWD:
        spi_cmd = SPI_CMD_MOVE_FWD;
        set_motors(PWM_CRUISE, PWM_CRUISE);
        break;
    case ACTION_BACK:
        spi_cmd = SPI_CMD_MOVE_BACK;
        set_motors(PWM_CRUISE, PWM_CRUISE);
        break;
    case ACTION_LEFT:
        spi_cmd = SPI_CMD_ROTATE_LEFT;
        set_motors(PWM_TURN, PWM_TURN);
        break;
    case ACTION_RIGHT:
        spi_cmd = SPI_CMD_ROTATE_RIGHT;
        set_motors(PWM_TURN, PWM_TURN);
        break;
    case ACTION_FWD_LEFT:
        spi_cmd = SPI_CMD_MOVE_FWD;
        set_motors(PWM_CRUISE/2, PWM_CRUISE);
        break;
    case ACTION_FWD_RIGHT:
        spi_cmd = SPI_CMD_MOVE_FWD;
        set_motors(PWM_CRUISE, PWM_CRUISE/2);
        break;
    case ACTION_BACK_LEFT:
        spi_cmd = SPI_CMD_MOVE_BACK;
        set_motors(PWM_CRUISE/2, PWM_CRUISE);
        break;
    case ACTION_BACK_RIGHT:
        spi_cmd = SPI_CMD_MOVE_BACK;
        set_motors(PWM_CRUISE, PWM_CRUISE/2);
        break;
    case ACTION_ATTACK:
        spi_cmd = SPI_CMD_MOVE_FWD;
        set_motors(PWM_MAX, PWM_MAX);
        break;
    case ACTION_ESTOP:
        spi_cmd = SPI_CMD_ESTOP;
        set_motors(0, 0);
        robot_state = STATE_ESTOP;
        state_entry_ms = sys_tick_ms;
        break;
    }
}

/* ================================================================
 * Telemetry Output (USART3)
 * ================================================================ */
__attribute__((unused))
static void usart3_putc(char c) {
    while (!(USART3->SR & USART_SR_TXE));
    USART3->DR = c;
}

#ifdef DEBUG_TELEMETRY
static void usart3_print(const char *s) {
    while (*s) usart3_putc(*s++);
}

static void usart3_print_hex(uint32_t val) {
    static const char hex[] = "0123456789ABCDEF";
    for (int i = 28; i >= 0; i -= 4) {
        usart3_putc(hex[(val >> i) & 0xF]);
    }
}

static void telemetry_output(void) {
    usart3_print("[BT] F:");
    usart3_print_hex(frame_count);
    usart3_print(" S:");
    usart3_putc('0' + robot_state);
    usart3_print(" D:");
    usart3_print_hex(vl53l1x_dist_mm);
    usart3_print(" B:");
    usart3_print_hex(battery_mv);
    usart3_print(" E:");
    usart3_print_hex((uint32_t)enc_a_delta);
    usart3_print("\r\n");
}
#endif

/* ================================================================
 * System Initialization
 * ================================================================ */

/* Clock: HSE 8MHz → PLL (M=8, N=336, P=2) → 168MHz
 * AHB = 168MHz, APB1 = 42MHz, APB2 = 84MHz
 */
void SystemInit(void) {
    /* Enable FPU */
    SCB_CPACR |= SCB_CPACR_FPU_ENABLE;
    __DSB();

#ifdef RENODE_SIM
    /* Simulation mode: skip HSE/PLL, use HSI (16MHz) */
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY));
    /* SW = HSI */
    RCC->CFGR = (RCC->CFGR & ~(3U << 0));
    while ((RCC->CFGR & (3U << 2)) != (0U << 2));
    /* SysTick @ 16MHz → 1ms */
    SysTick->LOAD = 16000000 / 1000 - 1;
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE | SysTick_CTRL_TICKINT | SysTick_CTRL_ENABLE;
    return;
#else
    /* Enable HSE */
    RCC->CR |= RCC_CR_HSEON;
    while (!(RCC->CR & RCC_CR_HSERDY));

    /* Configure PLL: M=8, N=336, P=2, Q=7, source=HSE */
    RCC->PLLCFGR = (8U << 0)    /* PLLM  */
                 | (336U << 6)  /* PLLN  */
                 | (0U << 16)   /* PLLP=2 (00) */
                 | (7U << 24);  /* PLLQ  */
    /* Set HSE as PLL source */
    RCC->PLLCFGR |= (1U << 22);

    /* Enable PLL */
    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY));

    /* Flash latency: 5 wait states for 168MHz */
    FLASH_ACR = FLASH_ACR_LATENCY_5WS | FLASH_ACR_PRFTEN | FLASH_ACR_ICEN | FLASH_ACR_DCEN;

    /* Set APB prescalers: APB1=/4 (42MHz), APB2=/2 (84MHz) */
    RCC->CFGR |= (5U << 10);  /* APB1 = /4 */
    RCC->CFGR |= (4U << 13);  /* APB2 = /2 */

    /* Switch system clock to PLL */
    RCC->CFGR |= (2U << 0);   /* SW = PLL */
    while ((RCC->CFGR & (3U << 2)) != (2U << 2));

    /* Configure SysTick: 1ms interrupt */
    SysTick->LOAD = SYSTEM_CLOCK_HZ / 1000 - 1;
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE | SysTick_CTRL_TICKINT | SysTick_CTRL_ENABLE;
#endif
}

/* GPIO init for peripherals */
static void gpio_init(void) {
    /* Enable GPIO clocks */
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOA | RCC_AHB1ENR_GPIOB | RCC_AHB1ENR_GPIOC;

    /* I2C1: PB6 (SCL), PB7 (SDA) → AF4, open-drain */
    GPIOB->MODER   &= ~((3U << 12) | (3U << 14));
    GPIOB->MODER   |=  (2U << 12) | (2U << 14);    /* AF mode */
    GPIOB->OTYPER  |=  (1U << 6) | (1U << 7);       /* Open-drain */
    GPIOB->OSPEEDR |=  (3U << 12) | (3U << 14);     /* High speed */
    GPIOB->PUPDR   |=  (1U << 12) | (1U << 14);     /* Pull-up */
    GPIOB->AFRL    |=  (4U << 24) | (4U << 28);     /* AF4 = I2C1 */

    /* SPI2: PB12 (NSS), PB13 (SCK), PB14 (MISO), PB15 (MOSI) → AF5 */
    GPIOB->MODER   &= ~((3U << 24) | (3U << 26) | (3U << 28) | (3U << 30));
    GPIOB->MODER   |=  (2U << 24) | (2U << 26) | (2U << 28) | (2U << 30);
    GPIOB->OSPEEDR |=  (3U << 24) | (3U << 26) | (3U << 28) | (3U << 30);
    GPIOB->AFRH    |=  (5U << 16) | (5U << 20) | (5U << 24) | (5U << 28);  /* AF5 = SPI2 */
    /* PB12: set as output initially (manual SS) */
    GPIOB->MODER   &= ~(3U << 24);
    GPIOB->MODER   |=  (1U << 24);    /* Output mode for NSS */
    GPIOB->ODR     |=  (1U << 12);    /* NSS high (inactive) */

    /* USART3: PB10 (TX), PB11 (RX) → AF7 */
    GPIOB->MODER   &= ~((3U << 20) | (3U << 22));
    GPIOB->MODER   |=  (2U << 20) | (2U << 22);
    GPIOB->AFRH    |=  (7U << 8) | (7U << 12);  /* AF7 = USART3 */
}

/* I2C1 init: 400kHz (Fast Mode) */
static void i2c1_init(void) {
    RCC->APB1ENR |= RCC_APB1ENR_I2C1;

    /* Reset I2C1 */
    I2C1->CR1 = 0;
    I2C1->CR1 |= I2C_CR1_PE;  /* Disable during config */
    I2C1->CR1 &= ~I2C_CR1_PE;

    /* Clock control: APB1=42MHz → CCR = 42MHz / (2*400kHz) = 52.5 ≈ 53 */
    I2C1->CCR = 53;
    I2C1->TRISE = 43;  /* 1000ns / (1/42MHz) + 1 */

    /* Enable I2C1 */
    I2C1->CR1 |= I2C_CR1_PE;
}

/* SPI2 init: Master, 5.25MHz, CPOL=1, CPHA=1, 8-bit */
static void spi2_init(void) {
    RCC->APB1ENR |= RCC_APB1ENR_SPI2;

    /* Reset SPI2 */
    SPI2->CR1 = 0;
    SPI2->CR2 = 0;

    /* Configure: Master, BR=fPCLK/8=42/8=5.25MHz, CPOL=1, CPHA=1 */
    SPI2->CR1 = (1U << SPI_CR1_BR_SHIFT)   /* BR = fPCLK/8 */
              | SPI_CR1_CPOL               /* CPOL=1 */
              | SPI_CR1_CPHA               /* CPHA=1 */
              | SPI_CR1_SSM                /* Software slave management */
              | SPI_CR1_SSI                /* Internal SS active */
              | SPI_CR1_MSTR;              /* Master mode */

    /* Enable SPI2 */
    SPI2->CR1 |= SPI_CR1_SPE;
}

/* USART3 init: 115200 baud, 8N1 */
static void usart3_init(void) {
    RCC->APB1ENR |= RCC_APB1ENR_USART3;

    /* Baud rate: APB1=42MHz → BRR = 42000000/115200 = 364.58 → 22.765 */
    USART3->BRR = (22U << 4) | 12U;  /* mantissa=22, fraction=12/16=0.75 */

    USART3->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}

/* IWDG init: 100ms timeout */
static void iwdg_init(void) {
    /* Unlock IWDG */
    IWDG->KR = IWDG_KR_KEY_ACCESS;

    /* Prescaler = /32 (LSI=32kHz → 1kHz) */
    IWDG->PR = 3;  /* /32 */

    /* Reload = 100 (100 * 1ms = 100ms) */
    IWDG->RLR = 100;

    /* Start IWDG */
    IWDG->KR = IWDG_KR_KEY_ENABLE;

    /* Initial refresh */
    IWDG->KR = IWDG_KR_KEY_REFRESH;
}

/* ================================================================
 * Main Entry Point
 * ================================================================ */
int main(void) {
    /* Hardware init */
    gpio_init();
    i2c1_init();
    spi2_init();
    usart3_init();
    iwdg_init();

    /* Sensor init */
    mpu6050_init();
    delay_ms(50);

    /* State init */
    robot_state = STATE_IDLE;
    state_entry_ms = sys_tick_ms;
    cylinder_detected = 0;

    /* Main loop: 100Hz */
    while (1) {
        /* Refresh watchdog */
        IWDG->KR = IWDG_KR_KEY_REFRESH;

        /* ========================================
         * FRAME START: Read sensors
         * ======================================== */
        /* VL53L1X: Read every 5th frame (20Hz) for non-blocking */
        if ((frame_count % 5) == 0) {
            vl53l1x_dist_mm = vl53l1x_read_range();

            /* Cylinder detection (3-frame convergence) */
            cylinder_detected = detect_cylinder(vl53l1x_dist_mm);
        }

        /* MPU6050: Read every frame (100Hz) */
        mpu6050_read_accel();

        /* ========================================
         * SPI exchange with F103
         * ======================================== */
        spi2_exchange_frame();

        /* ========================================
         * Emergency Stop Check
         * ======================================== */
        if (robot_state != STATE_ESTOP && check_estop()) {
            robot_state = STATE_ESTOP;
            state_entry_ms = sys_tick_ms;
        }

        /* ========================================
         * DQN Inference (every 2nd frame = 50Hz)
         * ======================================== */
        int action = ACTION_IDLE;
        if ((frame_count % 2) == 0 && robot_state != STATE_ESTOP) {
            build_observation();
            action = select_action();
        }

        /* ========================================
         * State Machine Update
         * ======================================== */
        if (robot_state != STATE_ESTOP) {
            state_machine_update();
        }

        /* ========================================
         * Action Execution
         * ======================================== */
        if (robot_state == STATE_ESTOP) {
            set_motors(0, 0);
            spi_cmd = SPI_CMD_ESTOP;
        } else {
            execute_action(action);
        }

        /* Build final SPI command frame with motor PWMs */
        /* (PWM values updated by execute_action, sent next frame) */

        /* ========================================
         * Telemetry
         * ======================================== */
#ifdef DEBUG_TELEMETRY
        if ((frame_count % 10) == 0) {
            telemetry_output();
        }
#endif

        /* ========================================
         * FRAME END: Timing control
         * ======================================== */
        frame_count++;

        /* Spin until 10ms elapsed */
        while ((sys_tick_ms - last_loop_ms) < MAIN_LOOP_PERIOD_MS) {
            __WFI();
        }
        last_loop_ms = sys_tick_ms;
    }

    return 0;  /* Never reached */
}
