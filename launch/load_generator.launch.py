"""Launch load_generator with parameters from config/monitors.yaml.

  ros2 launch generate_orbbec_launch load_generator.launch.py
  ros2 launch generate_orbbec_launch load_generator.launch.py config_file:=/path/to/your.yaml

The node idles until you call its service:
  ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
    "{mode: 'udp', target: 'gateway', rate_mbps: 500, duration_sec: 30}"
  ros2 service call /load_generator/stop std_srvs/srv/Trigger {}
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
            description='YAML parameter file for the load_generator node'),
        Node(
            package='generate_orbbec_launch',
            executable='load_generator',
            name='load_generator',
            output='screen',
            parameters=[config_file],
        ),
    ])
