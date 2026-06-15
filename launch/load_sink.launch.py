"""Launch load_sink with parameters from config/monitors.yaml.

Run this on the PEER machine (or the same host for a loopback test) so the
generator's tcp/udp/ros_pub traffic has a destination and a measured rx rate.

  ros2 launch generate_orbbec_launch load_sink.launch.py
  ros2 launch generate_orbbec_launch load_sink.launch.py config_file:=/path/to/your.yaml
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
            description='YAML parameter file for the load_sink node'),
        Node(
            package='generate_orbbec_launch',
            executable='load_sink',
            name='load_sink',
            output='screen',
            parameters=[config_file],
        ),
    ])
