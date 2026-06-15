"""Run two link_latency_monitor instances: end-to-end (internet) and gateway.

Topics are separated by node name:
  /link_latency_internet/latency  /link_latency_internet/outage   (target 8.8.8.8)
  /link_latency_gateway/latency   /link_latency_gateway/outage    (target 192.168.34.1)

  ros2 launch generate_orbbec_launch link_latency.launch.py
  ros2 launch generate_orbbec_launch link_latency.launch.py enable_gateway:=false
  ros2 launch generate_orbbec_launch link_latency.launch.py config_file:=/path/to/your.yaml
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_cfg = os.path.join(
        get_package_share_directory('generate_orbbec_launch'), 'config', 'monitors.yaml')
    config_file = LaunchConfiguration('config_file')
    enable_internet = LaunchConfiguration('enable_internet')
    enable_gateway = LaunchConfiguration('enable_gateway')

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file', default_value=default_cfg,
            description='YAML parameter file for the monitor nodes'),
        DeclareLaunchArgument(
            'enable_internet', default_value='true',
            description='Probe the end-to-end target (8.8.8.8)'),
        DeclareLaunchArgument(
            'enable_gateway', default_value='true',
            description='Probe the router/gateway (local first hop)'),

        Node(
            package='generate_orbbec_launch',
            executable='link_latency_monitor',
            name='link_latency_internet',
            output='screen',
            condition=IfCondition(enable_internet),
            parameters=[config_file],
        ),
        Node(
            package='generate_orbbec_launch',
            executable='link_latency_monitor',
            name='link_latency_gateway',
            output='screen',
            condition=IfCondition(enable_gateway),
            parameters=[config_file],
        ),
    ])
