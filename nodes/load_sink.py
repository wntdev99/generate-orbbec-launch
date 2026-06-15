#!/usr/bin/env python3
"""Receiver counterpart for load_generator -- run this on the peer machine.

Provides a destination so the tcp/udp engines and the ros_pub stream have
something to talk to, and reports the received rate:

  * TCP sink  : listens on tcp_port, accepts connections, drains and discards.
  * UDP sink  : binds udp_port, drains and discards datagrams.
  * ROS sink  : subscribes to `load_topic` (the generator's ~/load_topic) so the
                middleware pub/sub loop is complete and measurable -- this is what
                lets you see Fast DDS vs Zenoh receive throughput end to end.

Publishes:
  * ~/stats (generate_orbbec_launch/LoadStats) -- aggregate rx rate + totals
    (tx fields stay 0; this side only receives).
"""

import socket
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from std_msgs.msg import Header, UInt8MultiArray
from generate_orbbec_launch.msg import LoadStats


class LoadSink(Node):
    def __init__(self):
        super().__init__('load_sink')

        self.declare_parameter('tcp_port', 5201)
        self.declare_parameter('udp_port', 5201)
        self.declare_parameter('enable_tcp', True)
        self.declare_parameter('enable_udp', True)
        self.declare_parameter('enable_ros', True)
        self.declare_parameter('bind_host', '0.0.0.0')
        self.declare_parameter('recv_bufsize', 65536)
        # subscribe target: the generator publishes on <ns>/load_generator/load_topic
        self.declare_parameter('load_topic', '/load_generator/load_topic')
        self.declare_parameter('ros_reliable', True)
        self.declare_parameter('stats_period_sec', 1.0)
        self.declare_parameter('frame_id', '')

        self._tcp_port = int(self.get_parameter('tcp_port').value)
        self._udp_port = int(self.get_parameter('udp_port').value)
        self._bind = self.get_parameter('bind_host').value
        self._bufsize = int(self.get_parameter('recv_bufsize').value)
        self._frame_id = self.get_parameter('frame_id').value
        reliable = bool(self.get_parameter('ros_reliable').value)
        stats_period = float(self.get_parameter('stats_period_sec').value) or 1.0

        # rx counters (GIL keeps int +=/reads atomic enough for stats)
        self._rx_bytes = 0
        self._rx_msgs = 0
        self._errors = 0
        self._prev_rx = 0
        self._prev_t = time.monotonic()

        self._stop = threading.Event()
        self._threads = []
        self._sources = []

        if bool(self.get_parameter('enable_tcp').value):
            t = threading.Thread(target=self._tcp_server, daemon=True)
            self._threads.append(t)
            t.start()
            self._sources.append(f'tcp:{self._tcp_port}')
        if bool(self.get_parameter('enable_udp').value):
            t = threading.Thread(target=self._udp_server, daemon=True)
            self._threads.append(t)
            t.start()
            self._sources.append(f'udp:{self._udp_port}')
        if bool(self.get_parameter('enable_ros').value):
            topic = self.get_parameter('load_topic').value
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST, depth=10,
                reliability=(ReliabilityPolicy.RELIABLE if reliable
                             else ReliabilityPolicy.BEST_EFFORT))
            self._sub = self.create_subscription(
                UInt8MultiArray, topic, self._on_ros, qos)
            self._sources.append(f'ros:{topic}')

        self._pub = self.create_publisher(LoadStats, '~/stats', 10)
        self._timer = self.create_timer(stats_period, self._tick)
        self.get_logger().info('load_sink up: ' + ', '.join(self._sources or ['(no sources)']))

    # ---- TCP ---------------------------------------------------------------

    def _tcp_server(self):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self._bind, self._tcp_port))
            srv.listen(16)
            srv.settimeout(1.0)
        except OSError as exc:
            self._errors += 1
            self.get_logger().error(f'tcp bind {self._tcp_port} failed: {exc}')
            return
        with srv:
            while not self._stop.is_set():
                try:
                    conn, _addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                ct = threading.Thread(target=self._tcp_conn, args=(conn,), daemon=True)
                self._threads.append(ct)
                ct.start()

    def _tcp_conn(self, conn):
        with conn:
            conn.settimeout(2.0)
            while not self._stop.is_set():
                try:
                    data = conn.recv(self._bufsize)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                self._rx_bytes += len(data)
                self._rx_msgs += 1

    # ---- UDP ---------------------------------------------------------------

    def _udp_server(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self._bind, self._udp_port))
            sock.settimeout(1.0)
        except OSError as exc:
            self._errors += 1
            self.get_logger().error(f'udp bind {self._udp_port} failed: {exc}')
            return
        with sock:
            while not self._stop.is_set():
                try:
                    data, _addr = sock.recvfrom(self._bufsize)
                except socket.timeout:
                    continue
                except OSError:
                    break
                self._rx_bytes += len(data)
                self._rx_msgs += 1

    # ---- ROS ---------------------------------------------------------------

    def _on_ros(self, msg):
        self._rx_bytes += len(msg.data)
        self._rx_msgs += 1

    # ---- stats -------------------------------------------------------------

    def _tick(self):
        if not rclpy.ok():
            return
        now = time.monotonic()
        dt = now - self._prev_t
        rx_bps = max(0.0, (self._rx_bytes - self._prev_rx) / dt) if dt > 0 else 0.0
        self._prev_rx = self._rx_bytes
        self._prev_t = now

        out = LoadStats()
        out.header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self._frame_id)
        out.mode = 'sink'
        out.target = ', '.join(self._sources)
        out.running = rx_bps > 0.0
        out.rx_bps = rx_bps
        out.bytes_total = self._rx_bytes
        out.msgs_total = self._rx_msgs
        out.errors = self._errors
        self._pub.publish(out)

    def destroy_node(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = LoadSink()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
