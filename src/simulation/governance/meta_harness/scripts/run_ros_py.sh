#!/bin/bash
# run_ros_py.sh — run a python script inside the ROS2 Humble environment
# Usage: run_ros_py.sh /path/to/script.py [args...]
source /opt/ros/humble/setup.bash
source /home/ivy/bottlesumo_ws/install/setup.bash
export DISPLAY=:0
export LIBGL_ALWAYS_SOFTWARE=1
export FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/fastdds_udp.xml
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
exec python3 "$@"
