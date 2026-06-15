"""Launch net_throughput_monitor with parameters from config/monitors.yaml.

  ros2 launch generate_orbbec_launch net_throughput_monitor.launch.py
  ros2 launch generate_orbbec_launch net_throughput_monitor.launch.py config_file:=/path/to/your.yaml
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_cfg = os.path.join(
        get_package_share_directory('generate_orbbec_launch'), 'config', 'monitors.yaml')
    config_file = LaunchConfiguration('config_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file', default_value=default_cfg,
            description='YAML parameter file for the monitor nodes'),
        Node(
            package='generate_orbbec_launch',
            executable='net_throughput_monitor',
            name='net_throughput_monitor',
            output='screen',
            parameters=[config_file],
        ),
    ])
