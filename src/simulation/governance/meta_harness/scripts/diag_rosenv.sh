#!/bin/bash
# Diagnose ROS2 python environment for rclpy
echo "=== site-packages rcl/gazebo ==="
ls /opt/ros/humble/lib/python3.10/site-packages/ 2>/dev/null | grep -iE "rclpy|gazebo" || echo "NO rclpy/gazebo in site-packages"
echo "=== full listing (first 40) ==="
ls /opt/ros/humble/lib/python3.10/site-packages/ 2>/dev/null | head -40
echo "=== sourced import test ==="
source /opt/ros/humble/setup.bash
python3 -c "import rclpy; print('rclpy OK:', rclpy.__file__)"
echo "=== ament python path ==="
echo "PYTHONPATH=$PYTHONPATH"
