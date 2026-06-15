#!/usr/bin/env python3
"""Publish the router's WiFi WAN (uplink) signal as a ROS topic.

For a machine WIRED to the router, its own NIC has no dBm. But its internet
path still goes over the router's wireless uplink (WiFi WAN). This node reads
that uplink's signal from the router via SSH (`iwinfo <iface> info`) and
publishes it, so wired robots can still monitor the wireless leg of their link.

Publishes:
  * <node>/wifi_wan  (generate_orbbec_launch/WifiWanStatus)
  * /diagnostics     (diagnostic_msgs/DiagnosticArray)

Auth: uses SSH in BatchMode (key-based) -- NO password is stored. Set up a key
from this machine to the router first, e.g.:
    ssh-keygen -t ed25519
    ssh-copy-id root@<router>
For least privilege, restrict the key in the router's authorized_keys to only
run iwinfo (command="iwinfo ...").
"""

import re
import subprocess

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from std_msgs.msg import Header
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from generate_orbbec_launch.msg import WifiWanStatus


def parse_iwinfo(text):
    """Parse `iwinfo <iface> info` output into a dict (missing fields omitted)."""
    out = {}
    m = re.search(r'ESSID:\s*"([^"]*)"', text)
    if m:
        out['essid'] = m.group(1)
    m = re.search(r'Signal:\s*(-?\d+)\s*dBm', text)
    if m:
        out['signal_dbm'] = int(m.group(1))
    m = re.search(r'Noise:\s*(-?\d+)\s*dBm', text)
    if m:
        out['noise_dbm'] = int(m.group(1))
    m = re.search(r'Link Quality:\s*(\d+)/(\d+)', text)
    if m:
        out['quality'] = int(m.group(1))
        out['quality_max'] = int(m.group(2))
    m = re.search(r'Bit Rate:\s*([\d.]+)\s*MBit/s', text)
    if m:
        out['bitrate_mbps'] = float(m.group(1))
    return out


class WifiWanMonitor(Node):
    def __init__(self):
        super().__init__('wifi_wan_monitor')

        self.declare_parameter('router_host', '192.168.34.1')
        self.declare_parameter('router_user', 'root')
        self.declare_parameter('wan_iface', 'sta1')
        self.declare_parameter('poll_period_sec', 15.0)
        self.declare_parameter('ssh_timeout_sec', 8.0)
        self.declare_parameter('weak_warn_dbm', -70)   # WARN at/below this signal
        self.declare_parameter('weak_error_dbm', -80)  # ERROR at/below this signal
        self.declare_parameter('frame_id', '')

        self._host = self.get_parameter('router_host').value
        self._user = self.get_parameter('router_user').value
        self._iface = self.get_parameter('wan_iface').value
        self._ssh_timeout = float(self.get_parameter('ssh_timeout_sec').value)
        self._warn = int(self.get_parameter('weak_warn_dbm').value)
        self._error = int(self.get_parameter('weak_error_dbm').value)
        self._frame_id = self.get_parameter('frame_id').value
        period = float(self.get_parameter('poll_period_sec').value)
        if period <= 0.0:
            self.get_logger().warn(f'poll_period_sec={period} invalid; using 15.0')
            period = 15.0

        self._pub = self.create_publisher(WifiWanStatus, '~/wifi_wan', 10)
        self._diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)
        self._timer = self.create_timer(period, self.poll)

        self.get_logger().info(
            f'wifi_wan_monitor up: {self._user}@{self._host} iface={self._iface}, '
            f'period={period}s (SSH key/BatchMode; no password stored)')
        self.poll()

    def _query_router(self):
        """Return (ok, parsed_dict_or_error_string)."""
        cmd = [
            'ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', f'ConnectTimeout={int(self._ssh_timeout)}',
            f'{self._user}@{self._host}', f'iwinfo {self._iface} info',
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=self._ssh_timeout + 4)
        except subprocess.TimeoutExpired:
            return False, 'ssh timed out'
        except OSError as exc:
            return False, f'ssh failed to start: {exc}'
        if res.returncode != 0:
            err = (res.stderr or '').strip().splitlines()
            return False, (err[-1] if err else f'ssh exit {res.returncode}')
        return True, parse_iwinfo(res.stdout)

    def poll(self):
        if not rclpy.ok():
            return
        try:
            ok, data = self._query_router()
            now = self.get_clock().now().to_msg()

            msg = WifiWanStatus()
            msg.header = Header(stamp=now, frame_id=self._frame_id)
            msg.iface = self._iface
            msg.reachable = ok
            if ok:
                msg.essid = data.get('essid', '')
                msg.signal_dbm = data.get('signal_dbm', 0)
                msg.noise_dbm = data.get('noise_dbm', 0)
                msg.quality = data.get('quality', 0)
                msg.quality_max = data.get('quality_max', 0)
                msg.bitrate_mbps = data.get('bitrate_mbps', 0.0)
            self._pub.publish(msg)
            self._diag_pub.publish(self._build_diag(ok, data if ok else str(data), now))
        except Exception as exc:
            self.get_logger().warn(f'poll failed: {exc}')

    def _build_diag(self, ok, data, stamp):
        diag = DiagnosticArray()
        diag.header.stamp = stamp
        st = DiagnosticStatus()
        st.hardware_id = f'wifi_wan:{self._iface}'
        if not ok:
            st.name = f'wifi_wan: {self._iface}'
            st.level = DiagnosticStatus.ERROR
            st.message = f'router unreachable ({data}); SSH key set up?'
            st.values = [KeyValue(key='reachable', value='false')]
            diag.status.append(st)
            return diag

        sig = data.get('signal_dbm', 0)
        st.name = f"wifi_wan: {data.get('essid', self._iface)}"
        if sig <= self._error:
            st.level = DiagnosticStatus.ERROR
            st.message = f'very weak uplink {sig} dBm'
        elif sig <= self._warn:
            st.level = DiagnosticStatus.WARN
            st.message = f'weak uplink {sig} dBm'
        else:
            st.level = DiagnosticStatus.OK
            st.message = f'uplink {sig} dBm'
        st.values = [
            KeyValue(key='essid', value=str(data.get('essid', ''))),
            KeyValue(key='signal_dbm', value=str(sig)),
            KeyValue(key='noise_dbm', value=str(data.get('noise_dbm', 0))),
            KeyValue(key='quality', value=f"{data.get('quality', 0)}/{data.get('quality_max', 0)}"),
            KeyValue(key='bitrate_mbps', value=str(data.get('bitrate_mbps', 0.0))),
        ]
        diag.status.append(st)
        return diag


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = WifiWanMonitor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
