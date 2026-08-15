# BottleSumo Rev2 — Closed-Loop Simulation Verification Checklist

**Date**: 2026-07-29  
**Pipeline**: Gazebo (physics/sensors) ↔ HIL Bridge ↔ Renode (firmware)  
**Target**: 30 episodes, CTEA 1.5m sumo ring, bottle at (0.5, 0.3)

---

## Phase 0: Prerequisites ✅

| # | Check | Status |
|:-:|-------|:------:|
| 0.1 | URDF generated with mesh references | ✅ |
| 0.2 | STL meshes exported (6 pieces) | ✅ |
| 0.3 | Schematic netlist clean (I2C pullups populated) | ✅ |
| 0.4 | PCB 80×50mm layout generated | ✅ |
| 0.5 | SDF model with sensor plugins | ✅ |
| 0.6 | CTEA sumo ring world | ✅ |
| 0.7 | Renode dual-MCU script | ✅ |
| 0.8 | HIL bridge with episode runner | ✅ |

---

## Phase 1: Static Model Verification

### 1.1 URDF → SDF Conversion
```bash
cd bottlesumo_pi/models/cad
gz sdf -p bottlesumo_rev2.urdf > bottlesumo_rev2.sdf
# Verify: no conversion errors, all links preserved
```

| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 1.1.1 | All 10 links present | base_link + 6 sub-links + 3 sensors | ☐ |
| 1.1.2 | Mesh files resolve | No "file not found" warnings | ☐ |
| 1.1.3 | Collision geometry valid | Box/cylinder primitives | ☐ |
| 1.1.4 | Joints correctly typed | 2× continuous + 5× fixed | ☐ |
| 1.1.5 | Scale factor applied | STL mm→m (factor 0.001) | ☐ |

### 1.2 SDF Sensor Verification
```bash
# Launch Gazebo and inspect via GUI
gz sim bottlesumo_rev2.sdf
# Topics should appear: /bottlesumo/vl53l1x_bottle, /bottlesumo/vl53l0x_*
```

| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 1.2.1 | VL53L1X ray topic published | `/bottlesumo/vl53l1x_bottle` | ☐ |
| 1.2.2 | VL53L0X ×4 ray topics | 4 edge topics at 45° angles | ☐ |
| 1.2.3 | IMU topic @ 200Hz | `/bottlesumo/imu` | ☐ |
| 1.2.4 | Diff drive topics | `/bottlesumo/cmd_vel`, `/bottlesumo/odom` | ☐ |
| 1.2.5 | Ray noise within spec | VL53L0X ±3% @ 1m, VL53L1X ±3cm @ 1m | ☐ |

### 1.3 World Validation
```bash
gz sim ctea_sumo.world
# Inspect: ring visible (1.5m white + black border), bottle at (0.5, 0.3)
```

| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 1.3.1 | Ring surface 1.5m diameter | White disc | ☐ |
| 1.3.2 | Border visible | Black ring, 0.8m outer radius | ☐ |
| 1.3.3 | Wall collision active | Robot cannot leave ring | ☐ |
| 1.3.4 | Bottle target visible | Green cylinder at (0.5, 0.3) | ☐ |
| 1.3.5 | Opponent visible | Red box at (0.8, 0.2), facing center | ☐ |
| 1.3.6 | Friction on surface | Hardboard ~0.6 μ coefficient | ☐ |
| 1.3.7 | Gravity = -9.81 m/s² | Physics working | ☐ |

---

## Phase 2: Sensor Calibration (Sim-to-Hardware Mapping)

### 2.1 VL53L1X Bottle Detector Validation
```bash
python simulation/hil_bridge.py --episodes 1 --output calib_vl53l1x.json
# Place robot at various distances from bottle, verify range readings
```

| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 2.1.1 | Range @ 0.1m | 100mm ±5mm | ☐ |
| 2.1.2 | Range @ 0.5m | 500mm ±15mm | ☐ |
| 2.1.3 | Range @ 1.0m | 1000mm ±30mm | ☐ |
| 2.1.4 | Range @ 2.0m | 2000mm ±60mm | ☐ |
| 2.1.5 | Range @ 4.0m (max) | ~4000mm | ☐ |
| 2.1.6 | < 3cm returns 0 (too close) | Status=invalid | ☐ |
| 2.1.7 | Noise profile matches spec | σ=0.03 @ 1m (gaussian) | ☐ |

### 2.2 VL53L0X Edge Detectors
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 2.2.1 | All 4 sensors report independent ranges | 4 distinct values | ☐ |
| 2.2.2 | Range @ 0.03m (min) | 30mm ±5mm | ☐ |
| 2.2.3 | Range @ 1.0m | 1000mm ±30mm | ☐ |
| 2.2.4 | Range @ 2.0m (max) | 2000mm ±60mm | ☐ |
| 2.2.5 | Simultaneous edge detection triggers estop | All 4 < 3cm → motors stop | ☐ |

### 2.3 MPU6050 IMU
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 2.3.1 | Static accel Z | -9.81 m/s² (±0.02) | ☐ |
| 2.3.2 | Static gyro | 0 rad/s (±0.001) | ☐ |
| 2.3.3 | Tilt 30° roll → accel Y | ~sin(30°)×9.81 = 4.9 m/s² | ☐ |
| 2.3.4 | Gyro noise within spec | σ=0.01°/s | ☐ |
| 2.3.5 | 200Hz update rate | No drops over 10s window | ☐ |

### 2.4 Wheel Encoders
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 2.4.1 | 1 wheel revolution = 14,304 ticks | CPR×gearbox | ☐ |
| 2.4.2 | Encoder direction matches wheel | Forward = positive increment | ☐ |
| 2.4.3 | Noise < ±0.05 m/s (quantization) | Per spec | ☐ |

---

## Phase 3: Motor Control (Renode → Gazebo)

### 3.1 PWM → Velocity Mapping
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 3.1.1 | PWM=3600 (50%) → ~75 RPM | No-load speed 150 RPM | ☐ |
| 3.1.2 | PWM=7200 (100%) → ~150 RPM | Max no-load | ☐ |
| 3.1.3 | PWM=0 → 0 RPM | Motor stop | ☐ |
| 3.1.4 | Direction inversion correct | Left CCW, Right CW = forward | ☐ |
| 3.1.5 | STBY=0 → motors disabled | TB6612 standby | ☐ |
| 3.1.6 | PWM=10kHz no audible noise | Above hearing range | ☐ |

### 3.2 Motor Dynamics
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 3.2.1 | Stall torque ~0.015 N·m | N20 spec | ☐ |
| 3.2.2 | Acceleration < 2.0 m/s² | Diff drive limit | ☐ |
| 3.2.3 | Friction model active | Robot coasts briefly after stop | ☐ |

---

## Phase 4: SPI Communication (F407 ↔ F103)

### 4.1 Frame Integrity
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 4.1.1 | Master→Slave: 4 bytes per frame | cmd + args | ☐ |
| 4.1.2 | Slave→Master: 24 bytes per frame | sensor data + status | ☐ |
| 4.1.3 | CRC8 valid on all frames | No corruption | ☐ |
| 4.1.4 | Frame tail 0xAA present | Sync marker | ☐ |
| 4.1.5 | Frame rate = 100Hz (review #1) | 10ms interval | ☐ |

### 4.2 Timing Validation (Review #1: SPI rate mismatch)
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 4.2.1 | SPI frame interval measured | Mean=10ms, σ<1ms | ☐ |
| 4.2.2 | Master reads every 20ms (50Hz) | 2 frames per read cycle | ☐ |
| 4.2.3 | No buffer overflow | Queue never exceeds 3 frames | ☐ |
| 4.2.4 | Fallback: 50Hz unified mode | SPI → 50Hz if timing budget exceeded | ☐ |

---

## Phase 5: Safety Systems

### 5.1 Emergency Stop (Review #5)
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 5.1.1 | All 4 edges < 3cm → estop | PWM → 0 within 1ms | ☐ |
| 5.1.2 | Estop locked (no auto-recovery) | Motors remain at 0 | ☐ |
| 5.1.3 | Manual reset required | STBY toggle or re-power | ☐ |
| 5.1.4 | Estop during motor movement | Instant stop (no coasting) | ☐ |
| 5.1.5 | Estop log entry generated | entropy.log recorded | ☐ |

### 5.2 Watchdog (Review #9)
| # | Check | Expected | Pass? |
|:-:|-------|----------|:-----:|
| 5.2.1 | F407 IWDG enabled (100ms) | Renode watchdog active | ☐ |
| 5.2.2 | Task loop > 100ms → reset | Timeout triggers CPU reset | ☐ |
| 5.2.3 | F103 IWDG enabled | Aux MCU watchdog | ☐ |
| 5.2.4 | Watchdog kicked in main loop | Reset counter cleared every cycle | ☐ |

---

## Phase 6: 30-Episode Closed-Loop Test

### Run Command
```bash
# Terminal 1: Gazebo
gz sim simulation/gazebo/ctea_sumo.world &

# Terminal 2: Renode
renode simulation/renode/bottlesumo_rev2.resc &

# Terminal 3: HIL Bridge + Episode Runner
python simulation/hil_bridge.py --episodes 30 --output hil_results_30ep.json
```

### Per-Episode Metrics
| Episode | Bottle Detected | Edge Events | Estop Events | Duration (s) | Notes |
|:-------:|:--------------:|:-----------:|:------------:|:------------:|-------|
| 1 | ☐ | | | | |
| 2 | ☐ | | | | |
| ... | ... | ... | ... | ... | ... |
| 30 | ☐ | | | | |

### Aggregate Targets

| Metric | Target | Result | Pass? |
|--------|:------:|:------:|:-----:|
| Bottle detection rate | ≥ 80% (24/30) | | ☐ |
| False positive (phantom detection) | ≤ 10% | | ☐ |
| Edge events (near-fall) | ≤ 5 per episode avg | | ☐ |
| Emergency stop false triggers | ≤ 2 in 30 episodes | | ☐ |
| SPI frame drops | 0 | | ☐ |
| Estop lock functioning | 100% (no unintended recovery) | | ☐ |
| Watchdog resets | 0 | | ☐ |
| Avg episode duration | ≤ 15s (time-efficient) | | ☐ |

### Review Action Items Verified

| # | Issue | Verified By | Pass? |
|:-:|-------|------------|:-----:|
| 1 | SPI frame rate 100Hz vs 50Hz | Phase 4.2: timing validation | ☐ |
| 2 | F103 clock source HSE+PLL | Phase 0: Renode platform config | ☐ |
| 3 | VL53L1X non-blocking 20Hz | Phase 2.1: continuous mode verified | ☐ |
| 4 | Battery divider ratio 10k+3.3k | Phase 5: ADC simulation | ☐ |
| 5 | Estop lock + manual reset | Phase 5.1: lock verification | ☐ |
| 6 | Cylinder detection 3-frame rule | Phase 6: per-episode tracking | ☐ |
| 7 | BLE telemetry non-blocking | Phase 4: SPI timing still within budget | ☐ |
| 8 | I2C2 pullup 2.2kΩ (upgraded from 4.7kΩ) | Phase 2.2: 4× VL53L0X on same bus | ☐ |
| 9 | IWDG watchdog both MCUs | Phase 5.2: timeout test | ☐ |

---

## Phase 7: Additional Stress Tests

| # | Test | Description | Pass? |
|:-:|------|-------------|:-----:|
| 7.1 | Bottle at max range | 4m away → VL53L1X still detects within 3 frames | ☐ |
| 7.2 | Bottle partially occluded | 50% visible → DQN should still approach | ☐ |
| 7.3 | Opponent collision | Push force response, no damage | ☐ |
| 7.4 | Battery 6.4V (low) | Still drivable, ADC reading correct | ☐ |
| 7.5 | Battery 8.4V (full) | No regulation issues | ☐ |
| 7.6 | Motor stall (blocked wheel) | Overcurrent detection, safe shutdown | ☐ |
| 7.7 | I2C bus contention | 4× VL53L0X simultaneous reads, no data loss | ☐ |
| 7.8 | Ring edge approach | Robot detects border and turns before falling | ☐ |
| 7.9 | Continuous run (10min) | No memory leak, no thermal throttle | ☐ |
| 7.10 | Restart resilience | Simulated power cycle → boot sequence correct | ☐ |

---

## Go/No-Go Criteria

| Criterion | Threshold |
|-----------|-----------|
| **GO** (proceed to fabrication) | All P0 checks pass, bottle detection ≥ 80%, 0 estop false triggers |
| **CONDITIONAL GO** (fix then re-test) | ≥1 P0 failure but with known root cause |
| **NO-GO** (re-design required) | >2 P0 failures or unknown root cause |

---

*Generated by Meta-Harness Sim Pipeline*  
*Corresponds to review document: bottlesumo_rev2_architecture.md*
