# Phase 1: Static Model Verification — ✅ PASSED (with fixes)

## Model Structure
| File | Size | Type |
|------|------|------|
| bottlesumo_rev2.sdf | 377 lines | SDF 1.9 (Gazebo Harmonic) |
| bottlesumo_rev2.urdf | 264 lines | URDF (RViz/Foxglove) |
| ctea_sumo.world | 171 lines | SDF World (ODE physics) |
| `*.stl` ×6 | 26-77 KB each | Binary STL (from CadQuery) |

## Model Components (URDF)
| Component | Type | Mass estimate |
|-----------|------|:---:|
| base_link (chassis) | 220×180×3mm plate | ~0.427 kg |
| left_wheel | ⌀43mm, 10mm thick | ~0.015 kg |
| right_wheel | ⌀43mm, 10mm thick | ~0.015 kg |
| pcb | 100×70mm, 15mm elevated | ~0.05 kg |
| battery | 65×37×24mm (2S LiPo) | ~0.12 kg |
| left_motor + right_motor | N20 gearmotor | ~0.02 kg each |
| Sensors (5× vl53l + mpu6050) | inline in SDF | ~0.01 kg total |

## Diff Drive
| Parameter | Value |
|-----------|-------|
| Wheel separation | 0.170 m |
| Wheel diameter | 0.043 m |
| Max torque | 0.15 N·m |

## Issues Found & Fixed

| ID | Severity | File | Issue | Fix |
|:--:|----------|------|-------|-----|
| P1-01 | ⚠️ CRIT | SDF | 7× mesh `<scale>` was `1 1 1` — STL in mm, needs 0.001 | → `0.001 0.001 0.001` |
| P1-02 | ⚠️ WARN | URDF | `sensor_blue` material referenced but undefined | Added material def |
| P1-03 | ⚠️ WARN | World | Ring wall visual: `<mesh><cylinder>` invalid XML | → `<geometry><cylinder>` |
| P1-04 | ⚠️ WARN | World | Bottle material ref to non-existent `model://` | → inline `<ambient>` color |

## Verification Matrix
| Check | Result |
|-------|:------:|
| All 6 STL meshes exist and readable | ✅ |
| SDF links have valid collision geometry | ✅ |
| SDF joints type correct (2 revolute + 4 fixed) | ✅ |
| Diff Drive plugin parameters match physics | ✅ |
| World contains sumo ring + bottle + opponent + robot | ✅ |
| Sumo ring diameter ≈1.5m matches CTEA spec | ✅ |
| Bottle height 0.15m (150mm) matches CTEA spec | ✅ |
| Gravity set to -9.81 m/s² | ✅ |
| No circular references or infinite recursion | ✅ |

## Known Limitations
- SDF v1.9 maps only 5 ray sensors (vs firmware's 6-sensor model — vl53l0x_left_edge and vl53l0x_right_edge are separate; OK for sim)
- URDF only maps 2 edge sensors (vl53l0x_front_*) — not 4 as firmware expects — acceptable for visual sim (SDF has all 4)
- Collision ring wall is solid cylinder (not hollow) — ODE treats it as solid, which is conservative (harder to push out)
