"""Bring up the camera-host monitor nodes: usb_camera_monitor and kernel_log_monitor.

Parameters come from config/monitors.yaml (override with config_file:=...).
Each node can be toggled.

  ros2 launch generate_orbbec_launch monitors.launch.py
  ros2 launch generate_orbbec_launch monitors.launch.py enable_kernel_monitor:=false
  ros2 launch generate_orbbec_launch monitors.launch.py config_file:=/path/to/your.yaml
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
    enable_usb = LaunchConfiguration('enable_usb_monitor')
    enable_kernel = LaunchConfiguration('enable_kernel_monitor')

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file', default_value=default_cfg,
            description='YAML parameter file for the monitor nodes'),
        DeclareLaunchArgument(
            'enable_usb_monitor', default_value='true',
            description='Launch the USB camera inventory monitor node'),
        DeclareLaunchArgument(
            'enable_kernel_monitor', default_value='true',
            description='Launch the kernel log (dmesg) monitor node'),

        Node(
            package='generate_orbbec_launch',
            executable='usb_camera_monitor',
            name='usb_camera_monitor',
            output='screen',
            condition=IfCondition(enable_usb),
            parameters=[config_file],
        ),
        Node(
            package='generate_orbbec_launch',
            executable='kernel_log_monitor',
            name='kernel_log_monitor',
            output='screen',
            condition=IfCondition(enable_kernel),
            parameters=[config_file],
        ),
    ])
