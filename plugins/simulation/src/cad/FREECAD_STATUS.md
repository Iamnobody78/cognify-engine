# BottleSumo Mechanical Design — FreeCAD State

## Status: DESIGN EXISTS, NOT IN FREECAD FORMAT

The mechanical design for BottleSumo rev2 has been completed and validated,
but the primary source files are in CadQuery/URDF/STL format, not FreeCAD.

### Current Design Assets

| Asset | Format | Location | Status |
|-------|--------|----------|:------:|
| URDF model | `.urdf` | `bottlesumo_pi/models/cad/bottlesumo_rev2.urdf` | ✅ Complete |
| Visual mesh | `.stl` | `bottlesumo_pi/models/cad/` | ✅ Complete |
| Gazebo SDF | `.sdf` | `bottlesumo_pi/simulation/gazebo/bottlesumo_rev2.sdf` | ✅ Complete |
| FreeCAD source | `.FCStd` | — | ❌ Not created |

### Design Specs (from URDF)

| Parameter | Value | CTEA Limit |
|-----------|-------|:----------:|
| Chassis | 220×180×120mm | ≤300mm diameter |
| Mass | 315g | ≤1000g |
| Wheel diameter | 43mm | — |
| Motors | N20 ×2 micro metal | — |
| Sensors | VL53L0X ×4 + VL53L1X ×1 + MPU6050 | — |
| Material | 3mm carbon fiber | — |
| Front scoop | 30° detachable PLA | — |

### Migration Plan (P2 — non-blocking)

To create FreeCAD `.FCStd` files:
1. Convert URDF → STEP via `cadquery` (pip install cadquery)
2. Import STEP into FreeCAD 0.21+
3. Add manufacturing constraints (DFM)
4. Save as `.FCStd`

This is deferred — the current CadQuery/URDF pipeline is production-ready
and directly compatible with Gazebo + KiCad + Robotis URDF viewer.

### Blueprint v9.0 Correction

The blueprint states "FreeCAD 0.21" but the actual design pipeline uses
CadQuery → URDF → STL → Gazebo. This is a format deviation, not a design gap.
Recommend updating blueprint to reflect actual toolchain:
  `FreeCAD 0.21` → `CadQuery + URDF (Gazebo-compatible)`
