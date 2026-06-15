#!/usr/bin/env python3
"""Measure end-to-end latency / outages to a target (default 8.8.8.8).

Once per `period_sec` (default 1 s) it sends one ping with a `timeout_sec`
(default 1 s) deadline:
  * reply within timeout -> publish the RTT on ~/latency
  * no reply             -> publish ~/latency with valid=false, rtt_ms=NaN
An "outage" starts at the first failed probe and ends at the next reply; on
recovery a single ~/outage message is published with the outage duration, and
the running outage counter is incremented. Counters start at 0 each launch.

Publishes:
  * <node>/latency  (generate_orbbec_launch/PingLatency)  -- every period
  * <node>/outage   (generate_orbbec_launch/LinkOutage)   -- once per recovery
"""

import re
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from std_msgs.msg import Header
from generate_orbbec_launch.msg import PingLatency, LinkOutage

_RTT_RE = re.compile(r'time[=<]\s*([\d.]+)\s*ms')


def parse_ping_rtt(text):
    """Return RTT in ms from `ping -c1` output, or None if not found."""
    m = _RTT_RE.search(text)
    return float(m.group(1)) if m else None


class LinkLatencyMonitor(Node):
    def __init__(self):
        super().__init__('link_latency_monitor')

        self.declare_parameter('target', '8.8.8.8')
        self.declare_parameter('timeout_sec', 1.0)   # per-ping deadline = outage threshold
        self.declare_parameter('period_sec', 1.0)    # loop / publish period
        self.declare_parameter('frame_id', '')

        self._target = self.get_parameter('target').value
        self._timeout = float(self.get_parameter('timeout_sec').value)
        self._period = float(self.get_parameter('period_sec').value)
        if self._timeout <= 0.0:
            self._timeout = 1.0
        if self._period <= 0.0:
            self._period = 1.0
        self._frame_id = self.get_parameter('frame_id').value

        self._lat_pub = self.create_publisher(PingLatency, '~/latency', 10)
        self._out_pub = self.create_publisher(LinkOutage, '~/outage', 10)

        # outage state (counters start at 0 each launch)
        self._down_since = None   # monotonic time of first failure, or None if up
        self._outage_count = 0

        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self.get_logger().info(
            f'link_latency_monitor up: target={self._target}, '
            f'timeout={self._timeout}s, period={self._period}s')

    def _ping_once(self):
        """Return RTT in ms, or None on timeout/failure."""
        try:
            res = subprocess.run(
                ['ping', '-c', '1', '-W', str(self._timeout), self._target],
                capture_output=True, text=True, timeout=self._timeout + 2.0)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if res.returncode != 0:
            return None
        return parse_ping_rtt(res.stdout)

    def _on_sample(self, valid, now):
        """Update outage state. Return outage duration (s) when one just ended, else None."""
        if valid:
            if self._down_since is not None:
                duration = now - self._down_since
                self._down_since = None
                self._outage_count += 1
                return duration
            return None
        if self._down_since is None:
            self._down_since = now  # outage starts at first failure
        return None

    def _run(self):
        while not self._stop.is_set():
            start = time.monotonic()
            rtt = self._ping_once()
            if self._stop.is_set():
                break
            valid = rtt is not None
            duration = self._on_sample(valid, start)
            self._publish_latency(valid, rtt)
            if duration is not None:
                self._publish_outage(duration)
                self.get_logger().info(
                    f'{self._target}: recovered after {duration:.1f}s outage '
                    f'(total outages: {self._outage_count})')
            elif not valid and self._down_since is not None and start == self._down_since:
                self.get_logger().warn(f'{self._target}: outage started (no reply)')
            elapsed = time.monotonic() - start
            self._stop.wait(max(0.0, self._period - elapsed))

    def _publish_latency(self, valid, rtt):
        if not rclpy.ok():
            return
        msg = PingLatency()
        msg.header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self._frame_id)
        msg.target = self._target
        msg.valid = valid
        msg.rtt_ms = float(rtt) if valid else float('nan')
        msg.outage_count = self._outage_count
        self._lat_pub.publish(msg)

    def _publish_outage(self, duration_sec):
        if not rclpy.ok():
            return
        msg = LinkOutage()
        msg.header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self._frame_id)
        msg.target = self._target
        msg.duration_sec = float(duration_sec)
        msg.outage_count = self._outage_count
        self._out_pub.publish(msg)

    def destroy_node(self):
        self._stop.set()
        worker = getattr(self, '_worker', None)
        if worker is not None:
            worker.join(timeout=self._timeout + 3.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = LinkLatencyMonitor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
