"""
Shared action space and physical constants for BottleSumo lightweight simulation.

Used by: clone_v11_dagger.py, clone_v11_dagger_fast.py, strategy_zoo_fixed.py,
         irl_feature_matching.py, profiler_v2.py, tests/hil_dagger_test.py
"""

import math

# ── Physical constants ──────────────────────────────────────────────────────
RING_RADIUS = 1.0
ROBOT_RADIUS = 0.15
MAX_SPEED = 0.5
MAX_ANGULAR = math.pi
DT = 0.05
FRICTION = 0.9
RING_LIMIT = RING_RADIUS - ROBOT_RADIUS

# ── Observation / action dimensions ────────────────────────────────────────
OBS_DIM = 16
N_ACTIONS = 11

# ── Action space ───────────────────────────────────────────────────────────
ACTION_MAP = {
    0: (0.5, 0.0),          # FWD: strong forward
    1: (-0.3, 0.0),         # BACK: retreat
    2: (0.0, math.pi / 2),  # T_L: turn left
    3: (0.0, -math.pi / 2), # T_R: turn right
    4: (0.35, math.pi / 2), # F_L: forward-left
    5: (0.35, -math.pi / 2),# F_R: forward-right
    6: (-0.2, math.pi / 2), # B_L: back-left
    7: (-0.2, -math.pi / 2),# B_R: back-right
    8: (0.8, 0.0),          # PUSH: ram
    9: (0.0, 0.0),          # STOP: idle
    10: (0.0, math.pi),     # SPIN: 180 rotation
}

ACTION_NAMES = {
    0: "FWD",
    1: "BACK",
    2: "T_L",
    3: "T_R",
    4: "F_L",
    5: "F_R",
    6: "B_L",
    7: "B_R",
    8: "PUSH",
    9: "STOP",
    10: "SPIN",
}
