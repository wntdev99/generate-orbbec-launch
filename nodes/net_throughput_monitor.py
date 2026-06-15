#!/usr/bin/env python3
"""Publish per-interface network throughput (rx/tx bytes + rate).

Reads /sys/class/net/<iface>/statistics (no root). The interface can be
auto-detected from the active route (`ip route get`), so it adapts to any
machine's naming (eno1 / enp3s0 / wlp... ) and follows wired<->wifi failover.

Publishes:
  * <node>/throughput  (generate_orbbec_launch/NetThroughput)  -- one msg per
    interface per period.
"""

import os
import re
import subprocess
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from std_msgs.msg import Header
from generate_orbbec_launch.msg import NetThroughput

_DEV_RE = re.compile(r'\bdev\s+(\S+)')


def _read_int(path):
    try:
        with open(path) as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return 0


def egress_iface(target):
    """Interface the kernel would use to reach `target`, or None."""
    try:
        out = subprocess.run(['ip', 'route', 'get', target],
                             capture_output=True, text=True, timeout=3.0).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _DEV_RE.search(out)
    return m.group(1) if m else None


class NetThroughputMonitor(Node):
    def __init__(self):
        super().__init__('net_throughput_monitor')

        self.declare_parameter('interfaces', ['auto'])      # ['auto'] or explicit names
        self.declare_parameter('route_target', '8.8.8.8')   # used to resolve egress when 'auto'
        self.declare_parameter('period_sec', 1.0)
        self.declare_parameter('frame_id', '')

        ifaces = [i for i in self.get_parameter('interfaces').value if i]
        self._route_target = self.get_parameter('route_target').value
        self._frame_id = self.get_parameter('frame_id').value
        period = float(self.get_parameter('period_sec').value)
        if period <= 0.0:
            period = 1.0
        self._auto = (not ifaces) or any(i.lower() == 'auto' for i in ifaces)
        self._ifaces = ifaces

        self._pub = self.create_publisher(NetThroughput, '~/throughput', 10)
        self._prev = {}  # iface -> (rx_bytes, tx_bytes, monotonic_time)
        self._timer = self.create_timer(period, self.sample)

        mode = f'auto(route->{self._route_target})' if self._auto else self._ifaces
        self.get_logger().info(
            f'net_throughput_monitor up: interfaces={mode}, period={period}s')
        self.sample()

    def _resolve(self):
        if self._auto:
            ifc = egress_iface(self._route_target)
            return [ifc] if ifc else []
        return self._ifaces

    def sample(self):
        if not rclpy.ok():
            return
        try:
            now = time.monotonic()
            for ifc in self._resolve():
                base = f'/sys/class/net/{ifc}/statistics'
                if not os.path.isdir(base):
                    continue
                rx = _read_int(f'{base}/rx_bytes')
                tx = _read_int(f'{base}/tx_bytes')
                rx_bps = tx_bps = 0.0
                prev = self._prev.get(ifc)
                if prev:
                    dt = now - prev[2]
                    if dt > 0:
                        rx_bps = max(0.0, (rx - prev[0]) / dt)
                        tx_bps = max(0.0, (tx - prev[1]) / dt)
                self._prev[ifc] = (rx, tx, now)

                msg = NetThroughput()
                msg.header = Header(stamp=self.get_clock().now().to_msg(),
                                    frame_id=self._frame_id)
                msg.iface = ifc
                msg.rx_bytes = rx
                msg.tx_bytes = tx
                msg.rx_bps = rx_bps
                msg.tx_bps = tx_bps
                self._pub.publish(msg)
        except Exception as exc:
            self.get_logger().warn(f'sample failed: {exc}')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = NetThroughputMonitor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
