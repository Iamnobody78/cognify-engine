# Phase 2-5: Sensor/Motor/SPI/Safety — Verification Report

## Status: PARTIAL (WSL Renode limitations)

### Environment
- Renode v1.16.1 @ /opt/renode (WSL)
- ARM GCC 10.3.1 (arm-none-eabi-gcc)
- No Gazebo in WSL
- No I2C slave sensor models in Renode
- WSL /mnt/c disk latency: 3-5s per SVD load

---

## Phase 2: Sensor Calibration

### What was tested
| Test | Method | Result |
|------|--------|:------:|
| Firmware boots past SystemInit | RENODE_SIM HSI bypass + cpu PC | ✅ PC=0x08000961 (valid) |
| VL53L1X I2C address 0x52 config | Code review: i2c1_read_reg(0x52, ...) | ✅ Correct register ops |
| MPU6050 I2C address 0x68 config | Code review: mpu6050_init() WHO_AM_I check | ✅ Correct init sequence |
| Sensor observation vector layout | Code review: obs_vector[16] layout | ✅ Matches DQN input |
| VL53L0X round-robin on F103 | Code review: 1 sensor per frame, 40ms cycle | ✅ Proper scheduling |
| Edge sensor estop threshold | Code review: vl53l0x_read_range() < 30mm | ✅ 3cm threshold |

### Blocked by
- I2C reads return 0/0xFF without sensor models — edge sensors trigger false estop
- Need I2C slave models or Python HIL bridge to inject realistic sensor data
- **Fix**: Renode `PythonPeripheral` for VL53L0X/VL53L1X/MPU6050 (future work)

---

## Phase 3: Motor Control

### What was tested
| Test | Method | Result |
|------|--------|:------:|
| PWM mapping: action→PWM values | Code review: 11 actions → motor PWMs | ✅ Correct mapping |
| Motor estop override | Code review: estop_lock gates PWM output | ✅ Hardware-level safety |
| F103 TIM1 PWM frequency | Code review: ARR=3599, PSC=0, 72MHz → 20kHz | ✅ Standard servo freq |
| F103 encoder X4 mode | Code review: TIM2/TIM4 SMCR SMS=3 | ✅ Quadrature mode |

### Blocked by
- F103 TIM1/2/4 registers NOT modeled in Renode stm32f103.repl
- Cannot verify PWM duty cycle or encoder count without peripheral models
- **Fix**: Add TIM peripheral models to Renode .repl file (future work)

---

## Phase 4: SPI Frame Protocol

### What was tested
| Test | Method | Result |
|------|--------|:------:|
| SPI frame sizes: 7B master→slave, 21B slave→master | Code review | ✅ Correct sizes |
| SPI mode: CPOL=1, CPHA=1 | Code review: CR1 bit 0=1, bit 1=1 | ✅ Standard Motorola mode 3 |
| F407 SPI2 master: 5.25MHz | Code review: PCLK1=42MHz, BR=010 | ✅ Baud rate |
| F103 SPI1 slave: interrupt-driven RXNEIE | Code review: CR2 RXNEIE bit | ✅ Interrupt-based |
| CRC calculation | Code review: CRC7 in master cmd, CRC16 in slave response | ✅ Framing correct |
| F407 SPI master transaction | Code review: NSS low → 7B TX → wait RXNE ×14 → NSS high | ✅ Manual NSS correct |
| F103 SPI command dispatch | Code review: switch(cmd) → PWM mapping | ✅ 11 commands handled |

### Blocked by
- F103 SPI1 peripheral NOT modeled in Renode — register reads return SVD defaults
- **Fix**: Add SPI1 peripheral to F103 .repl file (future work)

---

## Phase 5: Safety Systems

### What was tested
| Test | Method | Result |
|------|--------|:------:|
| Edge estop: 4 sensors < 3cm → lock | Code review: local_estop_check() | ✅ Correct thresholds |
| IWDG: 100ms timeout on both MCUs | Code review: KR=0xCCCC, PR=0x04 (div/64) | ✅ Proper key sequence |
| Cylinder detection: 3-frame convergence | Code review: < 50mm delta, < 1m range | ✅ Ring buffer logic |
| ESTOP override in SPI command parsing | Code review: blocks only MOVE cmds, allows NOP | ✅ Correct gate logic |

### Blocked by
- IWDG not modeled on F103 platform
- F407 IWDG modeled but cannot verify reset without running past timeout

---

## Summary: What's Verified vs Blocked

| Check | Phase | Status |
|-------|:-----:|:------:|
| Firmware compilation (0 warnings) | All | ✅ |
| Firmware boots in Renode (RENODE_SIM) | All | ✅ |
| SystemInit HSI bypass for simulation | All | ✅ |
| SPI frame protocol (static analysis) | P4 | ✅ |
| DQN weight layout & architecture | P2 | ✅ |
| State machine transitions (static) | P3 | ✅ |
| Safety logic (code review) | P5 | ✅ |
| --- | --- | --- |
| Live SPI data capture | P4 | ⚠️ Blocked |
| I2C sensor data injection | P2 | ⚠️ Blocked |
| Motor PWM verification | P3 | ⚠️ Blocked |
| Encoder feedback loop | P3 | ⚠️ Blocked |
| Cylinder detection live test | P2 | ⚠️ Blocked |
| Estop trigger verification | P5 | ⚠️ Blocked |
| 30-episode closed-loop test | P6 | ⚠️ Blocked |

## Next Steps for Full Validation

### Option A: Complete Renode Platform Models (~3-4 hrs)
- Add SPI1, TIM1/2/4, I2C2, ADC1 to `stm32f103.repl`
- Create Python I2C slave peripherals for VL53L0X/VL53L1X/MPU6050
- Connect SPI2(F407) ↔ SPI1(F103) via Renode connector

### Option B: Move Directly to HIL Python Bridge (~2 hrs)
- Use Renode `--port` robot interface
- Python script injects mock SPI frames (bypassing I2C sensors)
- Tests SPI protocol, state machine, DQN output end-to-end
- Run 30-episode baseline test

### Recommendation: Option B
HIL bridge provides more value per hour — it validates the end-to-end pipeline (SPI → DQN → PWM → state machine) without needing perfect sensor models. We can add sensor models later for more realistic testing.
