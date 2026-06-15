#!/usr/bin/env python3
"""Publish the router's per-interface throughput (rx/tx bytes + rate) over SSH.

Reads /sys/class/net/<iface>/statistics on the router for the configured
interfaces (default WAN `sta1` and LAN `br-lan`) in a single SSH call, and
publishes one NetThroughput message per interface (distinguished by `iface`).

Auth: SSH BatchMode (key-based) -- NO password stored. Set up a key with
scripts/setup.sh --wifi-key (same key as wifi_wan_monitor uses).

Publishes:
  * <node>/throughput  (generate_orbbec_launch/NetThroughput)  -- one per iface per period
"""

import re
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from std_msgs.msg import Header
from generate_orbbec_launch.msg import NetThroughput

_IFACE_RE = re.compile(r'^[A-Za-z0-9._:-]+$')


def parse_stats(text):
    """Parse lines of '<iface> <rx_bytes> <tx_bytes>' into {iface: (rx, tx)}."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        ifc, rx, tx = parts
        try:
            out[ifc] = (int(rx), int(tx))
        except ValueError:
            continue
    return out


class RouterThroughputMonitor(Node):
    def __init__(self):
        super().__init__('router_throughput_monitor')

        self.declare_parameter('router_host', '192.168.34.1')
        self.declare_parameter('router_user', 'root')
        self.declare_parameter('interfaces', ['sta1', 'br-lan'])  # WAN, LAN
        self.declare_parameter('period_sec', 2.0)
        self.declare_parameter('ssh_timeout_sec', 8.0)
        self.declare_parameter('frame_id', '')

        self._host = self.get_parameter('router_host').value
        self._user = self.get_parameter('router_user').value
        self._ifaces = [i for i in self.get_parameter('interfaces').value
                        if i and _IFACE_RE.match(i)]
        self._ssh_timeout = float(self.get_parameter('ssh_timeout_sec').value)
        self._frame_id = self.get_parameter('frame_id').value
        period = float(self.get_parameter('period_sec').value)
        if period <= 0.0:
            period = 2.0

        self._pub = self.create_publisher(NetThroughput, '~/throughput', 10)
        self._prev = {}  # iface -> (rx, tx, monotonic)
        self._period = period
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self.get_logger().info(
            f'router_throughput_monitor up: {self._user}@{self._host} '
            f'interfaces={self._ifaces}, period={period}s (SSH key/BatchMode)')

    def _query(self):
        """Return raw stats text from the router, or None on failure."""
        remote = '; '.join(
            f'echo "{i} $(cat /sys/class/net/{i}/statistics/rx_bytes 2>/dev/null) '
            f'$(cat /sys/class/net/{i}/statistics/tx_bytes 2>/dev/null)"'
            for i in self._ifaces)
        cmd = [
            'ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', f'ConnectTimeout={int(self._ssh_timeout)}',
            f'{self._user}@{self._host}', remote,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=self._ssh_timeout + 4.0)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return None, str(exc)
        if res.returncode != 0:
            err = (res.stderr or '').strip().splitlines()
            return None, (err[-1] if err else f'ssh exit {res.returncode}')
        return res.stdout, None

    def _run(self):
        warned = False
        while not self._stop.is_set():
            start = time.monotonic()
            text, err = self._query()
            if self._stop.is_set():
                break
            if text is None:
                if not warned:
                    self.get_logger().warn(
                        f'router unreachable ({err}); SSH key set up? '
                        '(scripts/setup.sh --wifi-key)')
                    warned = True
            else:
                warned = False
                self._publish(parse_stats(text), start)
            elapsed = time.monotonic() - start
            self._stop.wait(max(0.0, self._period - elapsed))

    def _publish(self, stats, now):
        if not rclpy.ok():
            return
        for ifc, (rx, tx) in stats.items():
            rx_bps = tx_bps = 0.0
            prev = self._prev.get(ifc)
            if prev:
                dt = now - prev[2]
                if dt > 0:
                    rx_bps = max(0.0, (rx - prev[0]) / dt)
                    tx_bps = max(0.0, (tx - prev[1]) / dt)
            self._prev[ifc] = (rx, tx, now)

            msg = NetThroughput()
            msg.header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self._frame_id)
            msg.iface = ifc
            msg.rx_bytes = rx
            msg.tx_bytes = tx
            msg.rx_bps = rx_bps
            msg.tx_bps = tx_bps
            self._pub.publish(msg)

    def destroy_node(self):
        self._stop.set()
        worker = getattr(self, '_worker', None)
        if worker is not None:
            worker.join(timeout=self._ssh_timeout + 3.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = RouterThroughputMonitor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
