#!/bin/bash
# run_task007.sh — clean-stack + full TASK-007 harvest in one shot
# Usage: run_task007.sh [episodes] [tag]
set -e
EP=${1:-20}
TAG=${2:-TASK007_GAZEBO_VERIFY}
ROOT=/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/governance/meta_harness

echo "=== [TASK007] STEP 1/2: clean stack boot ==="
bash $ROOT/boot_gazebo_stack.sh > /tmp/task007_boot.log 2>&1 || true
grep -E 'ALIVE|spawn exit|Spawn status|service call exit' /tmp/task007_boot.log | head -6

echo "=== [TASK007] STEP 2/2: harvest $EP episodes ==="
source /opt/ros/humble/setup.bash
source /home/ivy/bottlesumo_ws/install/setup.bash
export DISPLAY=:0
export LIBGL_ALWAYS_SOFTWARE=1
export FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/fastdds_udp.xml
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
OUT=/tmp/task007_edges_${TAG}.json
python3 $ROOT/gazebo_edge_harvester.py --episodes $EP --tag $TAG --out $OUT
echo "=== [TASK007] harvest exit: $? ==="
