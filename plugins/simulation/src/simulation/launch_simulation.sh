#!/bin/bash
# ============================================================================
# launch_simulation.sh — BottleSumo Rev2 Full-Stack Simulation Launch
# ============================================================================
# Starts Gazebo (physics + sensors) + Renode (firmware) + HIL Bridge (glue)
# Runs 30-episode closed-loop validation.
#
# Usage:
#   bash simulation/launch_simulation.sh [--gui] [--episodes N]
#
# Prerequisites:
#   - Gazebo Harmonic installed (or Gazebo Classic with Ros2 bridge)
#   - Renode installed (v1.15+)
#   - Python 3.10+ with dependencies
#   - Firmware .elf files compiled
# ============================================================================

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
GAZEBO_DIR="$SCRIPT_DIR/gazebo"
RENODE_DIR="$SCRIPT_DIR/renode"
LOG_DIR="$PROJECT_DIR/logs/simulation"
NUM_EPISODES=30
USE_GUI=false

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --gui) USE_GUI=true; shift ;;
        --episodes) NUM_EPISODES="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
GAZEBO_LOG="$LOG_DIR/gazebo_$TIMESTAMP.log"
RENODE_LOG="$LOG_DIR/renode_$TIMESTAMP.log"
HIL_LOG="$LOG_DIR/hil_$TIMESTAMP.log"
HIL_OUTPUT="$LOG_DIR/hil_results_${TIMESTAMP}.json"

# ── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}═══ BottleSumo Rev2 Simulation Pipeline ═══${NC}"
echo "  Timestamp: $TIMESTAMP"
echo "  Episodes: $NUM_EPISODES"
echo "  GUI: $USE_GUI"
echo ""

# ── Step 1: Verify prerequisites ──────────────────────────────────
echo -e "${CYAN}[1/5] Checking prerequisites...${NC}"

check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "  ${RED}✗${NC} $1 not found — install and retry"
        MISSING_PREREQS=true
    else
        echo -e "  ${GREEN}✓${NC} $1 ($($1 --version 2>&1 | head -1))"
    fi
}

MISSING_PREREQS=false
check_cmd python3
check_cmd gz       # Gazebo Harmonic CLI
check_cmd renode   # Renode CLI

# Verify firmware .elf files exist
FIRMWARE_MAIN="$PROJECT_DIR/firmware/stm32_mcu/build/bottlesumo_main.elf"
FIRMWARE_AUX="$PROJECT_DIR/firmware/stm32_mcu/build/bottlesumo_aux.elf"
if [ ! -f "$FIRMWARE_MAIN" ]; then
    echo -e "  ${RED}✗${NC} Firmware not found: $FIRMWARE_MAIN"
    echo "    → Build first: cd $PROJECT_DIR/firmware/stm32_mcu && make"
    MISSING_PREREQS=true
else
    echo -e "  ${GREEN}✓${NC} F407 firmware: $FIRMWARE_MAIN"
fi
if [ ! -f "$FIRMWARE_AUX" ]; then
    echo -e "  ${RED}✗${NC} Firmware not found: $FIRMWARE_AUX"
    MISSING_PREREQS=true
else
    echo -e "  ${GREEN}✓${NC} F103 firmware: $FIRMWARE_AUX"
fi

# Verify SDF models
if [ ! -f "$GAZEBO_DIR/bottlesumo_rev2.sdf" ]; then
    echo -e "  ${RED}✗${NC} SDF model not found"
    MISSING_PREREQS=true
fi
if [ ! -f "$GAZEBO_DIR/ctea_sumo.world" ]; then
    echo -e "  ${RED}✗${NC} World file not found"
    MISSING_PREREQS=true
fi

if [ "$MISSING_PREREQS" = true ]; then
    echo -e "\n${RED}Prerequisites missing — aborting${NC}"
    exit 1
fi
echo -e "  ${GREEN}All prerequisites OK${NC}"

# ── Step 2: Export Gazebo model path ───────────────────────────────
echo -e "\n${CYAN}[2/5] Setting up Gazebo model paths...${NC}"
export GZ_SIM_RESOURCE_PATH="$GAZEBO_DIR:$PROJECT_DIR/models/cad:$GZ_SIM_RESOURCE_PATH"
echo "  GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH"

# ── Step 3: Launch Gazebo ─────────────────────────────────────────
echo -e "\n${CYAN}[3/5] Launching Gazebo...${NC}"

if [ "$USE_GUI" = true ]; then
    gz sim "$GAZEBO_DIR/ctea_sumo.world" &
else
    gz sim "$GAZEBO_DIR/ctea_sumo.world" --headless-rendering &
fi
GAZEBO_PID=$!
echo "  Gazebo PID: $GAZEBO_PID"

# Wait for Gazebo to be ready
echo "  Waiting for Gazebo to initialize..."
sleep 3
for i in {1..10}; do
    if gz topic -l 2>/dev/null | grep -q "/bottlesumo"; then
        echo -e "  ${GREEN}✓${NC} Gazebo ready (topics detected)"
        break
    fi
    sleep 1
done

# ── Step 4: Launch Renode ─────────────────────────────────────────
echo -e "\n${CYAN}[4/5] Launching Renode...${NC}"

# Update Renode script with correct firmware paths
sed -i.bak \
    -e "s|# sysbus LoadELF.*bottlesumo_main.elf|sysbus LoadELF @$FIRMWARE_MAIN|" \
    -e "s|# sysbus LoadELF.*bottlesumo_aux.elf|sysbus LoadELF @$FIRMWARE_AUX|" \
    "$RENODE_DIR/bottlesumo_rev2.resc"

renode "$RENODE_DIR/bottlesumo_rev2.resc" &
RENODE_PID=$!
echo "  Renode PID: $RENODE_PID"
sleep 2
echo -e "  ${GREEN}✓${NC} Renode started (GDB on :3333 and :3334)"

# ── Step 5: Launch HIL Bridge ─────────────────────────────────────
echo -e "\n${CYAN}[5/5] Launching HIL Bridge + Episode Runner...${NC}"

python3 "$SCRIPT_DIR/hil_bridge.py" \
    --gazebo-uri "http://localhost:11345" \
    --renode-port 3333 \
    --renode-aux-port 3334 \
    --episodes "$NUM_EPISODES" \
    --output "$HIL_OUTPUT" &
HIL_PID=$!
echo "  HIL Bridge PID: $HIL_PID"

# ── Wait for completion ───────────────────────────────────────────
echo -e "\n${CYAN}═══ Simulation running — waiting for $NUM_EPISODES episodes... ═══${NC}"
wait $HIL_PID

# ── Cleanup ───────────────────────────────────────────────────────
echo -e "\n${CYAN}═══ Shutting down... ═══${NC}"
kill $GAZEBO_PID 2>/dev/null || true
kill $RENODE_PID 2>/dev/null || true

# Restore Renode script
mv "$RENODE_DIR/bottlesumo_rev2.resc.bak" "$RENODE_DIR/bottlesumo_rev2.resc" 2>/dev/null || true

echo -e "${GREEN}═══ Simulation complete ═══${NC}"
echo "  Results: $HIL_OUTPUT"
echo "  Gazebo log: $GAZEBO_LOG"
echo "  Renode log: $RENODE_LOG"
