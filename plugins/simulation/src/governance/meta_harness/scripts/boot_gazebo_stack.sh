#!/bin/bash
# TASK-007: boot Gazebo stack with FastDDS UDP-only transport + spawn robot + probe services
set -x
source /opt/ros/humble/setup.bash
source /home/ivy/bottlesumo_ws/install/setup.bash
export DISPLAY=:0
export LIBGL_ALWAYS_SOFTWARE=1
export FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/fastdds_udp.xml
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# clean stale state
pkill -9 -f gzserver 2>/dev/null
pkill -9 -f spawn_entity 2>/dev/null
pkill -9 -f "ros2 daemon" 2>/dev/null
rm -f /dev/shm/fastrtps* /dev/shm/sem.fastrtps* 2>/dev/null
sleep 1

# boot gzserver (arena_mini_fast world: 5ms physics for RTF, + ros init/factory/state plugins)
nohup gzserver -s libgazebo_ros_init.so -s libgazebo_ros_factory.so -s libgazebo_ros_state.so \
  /tmp/arena_mini_fast.sdf \
  > /tmp/gzserver.log 2>&1 &
echo "gzserver pid: $!"
sleep 18
echo "=== gzserver alive? ==="
pgrep -f gzserver >/dev/null && echo ALIVE || (echo DEAD; tail -20 /tmp/gzserver.log)

# spawn robot
ros2 run gazebo_ros spawn_entity.py -entity bottlesumo -file /tmp/bottlesumo.urdf -x 0 -y 0 -z 0.03 \
  > /tmp/spawn.log 2>&1
echo "spawn exit: $?"
tail -3 /tmp/spawn.log

# probe model list via service (timeout guard)
timeout 15 ros2 service call /get_model_list gazebo_msgs/srv/GetModelList "{}" > /tmp/msvc.log 2>&1
echo "service call exit: $?"
tail -8 /tmp/msvc.log

echo "=== model_states topic? ==="
timeout 8 ros2 topic echo /gazebo/model_states gazebo_msgs/msg/ModelStates --once > /tmp/model_states.log 2>&1
echo "topic echo exit: $?"
head -20 /tmp/model_states.log
