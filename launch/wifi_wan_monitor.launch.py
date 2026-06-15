"""Launch wifi_wan_monitor with parameters from config/monitors.yaml.

  ros2 launch generate_orbbec_launch wifi_wan_monitor.launch.py
  ros2 launch generate_orbbec_launch wifi_wan_monitor.launch.py config_file:=/path/to/your.yaml

Requires an SSH key from this machine to the router (see scripts/setup.sh --wifi-key).
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
            executable='wifi_wan_monitor',
            name='wifi_wan_monitor',
            output='screen',
            parameters=[config_file],
        ),
    ])
