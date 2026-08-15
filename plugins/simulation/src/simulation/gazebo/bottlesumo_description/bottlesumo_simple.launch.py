"""BottleSumo launch -- proven YAML params-file approach.
Sequence: RSP first (3s) -> Gazebo (5s) -> Spawn.

Uses __file__-based path resolution (avoiding FindPackageShare.perform(None) crash).
"""
import os
import yaml
import tempfile
import subprocess

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    RegisterEventHandler,
    TimerAction,
    LogInfo,
)
from launch.event_handlers import OnProcessStart
from launch_ros.actions import Node

# Resolve package root from this file's location:
# launch/bottlesumo_simple.launch.py -> ../../ = package root
_THIS_FILE = os.path.abspath(__file__)
_PKG_ROOT = os.path.dirname(os.path.dirname(_THIS_FILE))

# Build paths at module load time (no LaunchContext needed)
_XACRO_PATH = os.path.join(_PKG_ROOT, 'urdf', 'bottlesumo.urdf.xacro')
_WORLD_PATH = os.path.join(_PKG_ROOT, 'worlds', 'arena_mini.sdf')
_ROS_LIB = '/opt/ros/humble/lib'


def _generate_params():
    """Generate YAML params file with robot_description URDF."""
    result = subprocess.run(
        ['xacro', _XACRO_PATH],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f'xacro failed:\n{result.stderr}')
    urdf_str = result.stdout

    params = {'/**': {'ros__parameters': {'robot_description': urdf_str}}}
    params_path = os.path.join(tempfile.gettempdir(), 'bottlesumo_params.yaml')
    with open(params_path, 'w') as f:
        yaml.dump(params, f)

    print(f'[bottlesumo_simple] Generated params: {len(urdf_str)} bytes URDF')
    return params_path


# Generate params at import time (once, cached)
_PARAMS_PATH = _generate_params()


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),

        # Phase 1: RSP (MUST start first for DDS discovery)
        LogInfo(msg='[bottlesumo_simple] Phase 1: Starting RSP...'),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[_PARAMS_PATH],
            arguments=['--ros-args', '--log-level', 'info'],
        ),

        # Phase 2: Gazebo (delayed 3s after RSP, gives DDS time)
        LogInfo(msg='[bottlesumo_simple] Phase 2: Gazebo starting in 3s...'),
        TimerAction(
            period=3.0,
            actions=[
                ExecuteProcess(
                    cmd=[
                        'gzserver',
                        '-s', 'libgazebo_ros_init.so',
                        '-s', 'libgazebo_ros_factory.so',
                        _WORLD_PATH,
                    ],
                    output='screen',
                    name='gazebo',
                    additional_env={
                        'GAZEBO_PLUGIN_PATH': _ROS_LIB,
                        'LD_LIBRARY_PATH': f'{_ROS_LIB}:{os.environ.get("LD_LIBRARY_PATH", "")}',
                    },
                ),
            ],
        ),

        # Phase 3: Spawn (delayed 11s = 3s RSP + 8s Gazebo init)
        LogInfo(msg='[bottlesumo_simple] Phase 3: Spawning robot in 11s...'),
        TimerAction(
            period=11.0,
            actions=[
                ExecuteProcess(
                    cmd=[
                        'ros2', 'run', 'gazebo_ros', 'spawn_entity.py',
                        '-topic', 'robot_description',
                        '-entity', 'bottlesumo',
                        '-x', '0', '-y', '0', '-z', '0.0',
                        '-timeout', '60',
                    ],
                    output='screen',
                    name='spawn_entity',
                ),
            ],
        ),
    ])
