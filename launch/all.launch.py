"""Bring up ALL monitor nodes at once (everything ON by default).

Composes the per-group launch files and shares one config file
(config/monitors.yaml). Toggle each group on/off:

  ros2 launch generate_orbbec_launch all.launch.py
  ros2 launch generate_orbbec_launch all.launch.py enable_wifi_wan:=false
  ros2 launch generate_orbbec_launch all.launch.py config_file:=/path/to/your.yaml

Nodes: usb_camera_monitor, kernel_log_monitor, wifi_wan_monitor,
       link_latency_internet, link_latency_gateway.
Note: wifi_wan_monitor needs an SSH key to the router (scripts/setup.sh --wifi-key);
      otherwise it stays up and reports ERROR on /diagnostics.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    pkg_share = get_package_share_directory('generate_orbbec_launch')
    launch_dir = os.path.join(pkg_share, 'launch')
    default_cfg = os.path.join(pkg_share, 'config', 'monitors.yaml')

    config_file = LaunchConfiguration('config_file')
    enable_usb = LaunchConfiguration('enable_usb_monitor')
    enable_kernel = LaunchConfiguration('enable_kernel_monitor')
    enable_wifi_wan = LaunchConfiguration('enable_wifi_wan')
    enable_link_latency = LaunchConfiguration('enable_link_latency')
    enable_net_throughput = LaunchConfiguration('enable_net_throughput')
    enable_router_throughput = LaunchConfiguration('enable_router_throughput')

    def include(filename, condition=None, extra=None):
        args = {'config_file': config_file}
        if extra:
            args.update(extra)
        kwargs = {'launch_arguments': args.items()}
        if condition is not None:
            kwargs['condition'] = IfCondition(condition)
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(launch_dir, filename)), **kwargs)

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file', default_value=default_cfg,
            description='Shared YAML parameter file for all monitor nodes'),
        DeclareLaunchArgument('enable_usb_monitor', default_value='true',
                              description='usb_camera_monitor'),
        DeclareLaunchArgument('enable_kernel_monitor', default_value='true',
                              description='kernel_log_monitor'),
        DeclareLaunchArgument('enable_wifi_wan', default_value='true',
                              description='wifi_wan_monitor (needs router SSH key)'),
        DeclareLaunchArgument('enable_link_latency', default_value='true',
                              description='link_latency internet + gateway instances'),
        DeclareLaunchArgument('enable_net_throughput', default_value='true',
                              description='net_throughput_monitor (host NIC rx/tx)'),
        DeclareLaunchArgument('enable_router_throughput', default_value='true',
                              description='router_throughput_monitor (WAN/LAN rx/tx, needs SSH key)'),

        # usb + kernel (their own per-node toggles are passed through)
        include('monitors.launch.py', extra={
            'enable_usb_monitor': enable_usb,
            'enable_kernel_monitor': enable_kernel,
        }),
        include('wifi_wan_monitor.launch.py', condition=enable_wifi_wan),
        include('link_latency.launch.py', condition=enable_link_latency),
        include('net_throughput_monitor.launch.py', condition=enable_net_throughput),
        include('router_throughput_monitor.launch.py', condition=enable_router_throughput),
    ])
