"""Bring up both monitor nodes: usb_camera_monitor and kernel_log_monitor.

Hand-authored launch file (tracked in git, unlike the generated multi_camera_*
launch files). Each node can be toggled and its key parameters overridden.

Examples:
  ros2 launch generate_orbbec_launch monitors.launch.py
  ros2 launch generate_orbbec_launch monitors.launch.py enable_kernel_monitor:=false
  ros2 launch generate_orbbec_launch monitors.launch.py kernel_max_priority:=4
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    enable_usb = LaunchConfiguration('enable_usb_monitor')
    enable_kernel = LaunchConfiguration('enable_kernel_monitor')
    usb_poll_period = LaunchConfiguration('usb_poll_period_sec')
    kernel_max_priority = LaunchConfiguration('kernel_max_priority')
    kernel_include_backlog = LaunchConfiguration('kernel_include_backlog')

    return LaunchDescription([
        DeclareLaunchArgument(
            'enable_usb_monitor', default_value='true',
            description='Launch the USB camera inventory monitor node'),
        DeclareLaunchArgument(
            'enable_kernel_monitor', default_value='true',
            description='Launch the kernel log (dmesg) monitor node'),
        DeclareLaunchArgument(
            'usb_poll_period_sec', default_value='2.0',
            description='usb_camera_monitor sysfs poll period (seconds)'),
        DeclareLaunchArgument(
            'kernel_max_priority', default_value='7',
            description='kernel_log_monitor: publish entries with priority <= this (0..7)'),
        DeclareLaunchArgument(
            'kernel_include_backlog', default_value='false',
            description='kernel_log_monitor: also emit recent backlog lines on startup'),

        Node(
            package='generate_orbbec_launch',
            executable='usb_camera_monitor',
            name='usb_camera_monitor',
            output='screen',
            condition=IfCondition(enable_usb),
            parameters=[{
                'poll_period_sec': ParameterValue(usb_poll_period, value_type=float),
            }],
        ),
        Node(
            package='generate_orbbec_launch',
            executable='kernel_log_monitor',
            name='kernel_log_monitor',
            output='screen',
            condition=IfCondition(enable_kernel),
            parameters=[{
                'max_priority': ParameterValue(kernel_max_priority, value_type=int),
                'include_backlog': ParameterValue(kernel_include_backlog, value_type=bool),
            }],
        ),
    ])
