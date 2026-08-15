#!/bin/bash
# TASK-007 diag: launch Gazebo stack, capture full logs, list services
WS=/home/ivy/bottlesumo_ws
export DISPLAY=:99
pkill -f Xvfb 2>/dev/null; pkill -f gzserver 2>/dev/null; pkill -f robot_state_publisher 2>/dev/null
sleep 1
Xvfb :99 -screen 0 1280x720x24 -ac >/dev/null 2>&1 &
sleep 1
source /opt/ros/humble/setup.bash
source $WS/install/setup.bash
timeout 45 ros2 launch bottlesumo_description bottlesumo_simple.launch.py > /tmp/gazebo_launch.log 2>&1 &
LAUNCH_PID=$!
sleep 25
echo "=== /tmp/gazebo_launch.log (tail 60) ==="
tail -60 /tmp/gazebo_launch.log
echo "=== ros2 service list (gazebo-related) ==="
timeout 10 ros2 service list 2>/dev/null | grep -i gazebo || echo "NO gazebo services"
echo "=== ros2 node list ==="
timeout 10 ros2 node list 2>/dev/null | head -20
echo "=== gzserver procs ==="
pgrep -af gzserver | head -5
kill $LAUNCH_PID 2>/dev/null
pkill -f gzserver 2>/dev/null; pkill -f robot_state_publisher 2>/dev/null; pkill -f Xvfb 2>/dev/null
echo "=== DONE ==="
