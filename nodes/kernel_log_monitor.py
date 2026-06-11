#!/usr/bin/env python3
"""Publish camera/USB-related kernel log lines as a ROS topic.

Ubuntu sets kernel.dmesg_restrict=1 by default, so reading /dev/kmsg or
`dmesg` directly requires root / CAP_SYSLOG. Instead this node follows the
systemd journal's kernel stream via `journalctl -k -f`, which a user in the
`adm` or `systemd-journal` group can read WITHOUT root. Lines matching the
configured keywords (usb / uvcvideo / xhci / orbbec / ...) are published.

Publishes:
  * <node>/kernel_log  (generate_orbbec_launch/KernelLogEntry)
  * /diagnostics       (diagnostic_msgs/DiagnosticArray) - rolling severity summary
"""

import json
import shutil
import subprocess
import threading

import rclpy
from rclpy.node import Node

from std_msgs.msg import Header
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from generate_orbbec_launch.msg import KernelLogEntry

_PRIORITY_LABELS = {
    0: 'emerg', 1: 'alert', 2: 'crit', 3: 'err',
    4: 'warning', 5: 'notice', 6: 'info', 7: 'debug',
}


class KernelLogMonitor(Node):
    def __init__(self):
        super().__init__('kernel_log_monitor')

        self.declare_parameter('keywords', ['usb', 'uvcvideo', 'xhci', 'orbbec', '2bc5'])
        self.declare_parameter('max_priority', 7)          # publish entries with priority <= this
        self.declare_parameter('include_backlog', False)   # also emit recent existing journal lines
        self.declare_parameter('backlog_lines', 50)        # how many recent lines when include_backlog
        self.declare_parameter('frame_id', '')

        self._keywords = [k.lower() for k in self.get_parameter('keywords').value if k]
        self._max_priority = int(self.get_parameter('max_priority').value)
        self._backlog_lines = int(self.get_parameter('backlog_lines').value)
        self._frame_id = self.get_parameter('frame_id').value
        backlog = bool(self.get_parameter('include_backlog').value)

        self._pub = self.create_publisher(KernelLogEntry, '~/kernel_log', 50)
        self._diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)

        # rolling state for the diagnostic summary
        self._lock = threading.Lock()
        self._counts = {'err': 0, 'warn': 0, 'info': 0}
        self._last_message = ''
        self._worst = DiagnosticStatus.OK

        self._proc = None
        self._reader = None
        self._stop = threading.Event()

        self.create_timer(5.0, self._publish_diagnostics)

        if self._start_journalctl(backlog):
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            self.get_logger().info(
                f'kernel_log_monitor up: keywords={self._keywords}, '
                f'max_priority={self._max_priority}, backlog={backlog}')

    def _start_journalctl(self, backlog):
        if shutil.which('journalctl') is None:
            msg = 'journalctl not found; cannot follow kernel log'
            self.get_logger().error(msg)
            self._set_unavailable(msg)
            return False
        cmd = ['journalctl', '-k', '-f', '-o', 'json']
        # -n controls how much history precedes following:
        #   no backlog       -> -n 0    (only new lines from now on)
        #   include_backlog  -> -n N    (last N kernel lines, then follow)
        cmd += ['-n', str(self._backlog_lines) if backlog else '0']
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1)
        except OSError as exc:
            msg = f'failed to start journalctl: {exc}'
            self.get_logger().error(msg)
            self._set_unavailable(msg)
            return False
        return True

    def _set_unavailable(self, reason):
        with self._lock:
            self._worst = DiagnosticStatus.ERROR
            self._last_message = reason

    def _read_loop(self):
        proc = self._proc
        for line in proc.stdout:
            if self._stop.is_set():
                break
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._handle(entry)
        # stream ended unexpectedly -> most likely a permission problem
        if not self._stop.is_set():
            err = ''
            if proc.stderr is not None:
                err = (proc.stderr.read() or '').strip()
            msg = err or ('journalctl stream ended; check that the user is in the '
                          'adm or systemd-journal group')
            self.get_logger().error(msg)
            self._set_unavailable(msg)

    def _handle(self, entry):
        message = entry.get('MESSAGE', '')
        if isinstance(message, list):  # journal encodes binary payloads as a byte list
            try:
                message = bytes(message).decode('utf-8', 'replace')
            except (ValueError, TypeError):
                message = str(message)
        matched = next((k for k in self._keywords if k in message.lower()), None)
        if matched is None:
            return
        try:
            priority = int(entry.get('PRIORITY', 6))
        except (ValueError, TypeError):
            priority = 6
        if priority > self._max_priority:
            return
        try:
            realtime_us = int(entry.get('__REALTIME_TIMESTAMP', 0))
        except (ValueError, TypeError):
            realtime_us = 0

        msg = KernelLogEntry()
        msg.header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self._frame_id)
        msg.priority = priority
        msg.priority_label = _PRIORITY_LABELS.get(priority, str(priority))
        msg.realtime_us = realtime_us
        msg.message = message
        msg.matched_keyword = matched
        self._pub.publish(msg)

        with self._lock:
            if priority <= 3:
                self._counts['err'] += 1
                self._worst = max(self._worst, DiagnosticStatus.ERROR)
            elif priority == 4:
                self._counts['warn'] += 1
                self._worst = max(self._worst, DiagnosticStatus.WARN)
            else:
                self._counts['info'] += 1
            self._last_message = message

    def _publish_diagnostics(self):
        with self._lock:
            counts = dict(self._counts)
            worst = self._worst
            last = self._last_message
        diag = DiagnosticArray()
        diag.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = 'kernel_log: camera/usb'
        status.hardware_id = 'kernel_log'
        status.level = worst
        status.message = last or 'monitoring kernel log'
        status.values = [
            KeyValue(key='err_count', value=str(counts['err'])),
            KeyValue(key='warn_count', value=str(counts['warn'])),
            KeyValue(key='info_count', value=str(counts['info'])),
        ]
        diag.status.append(status)
        self._diag_pub.publish(diag)

    def destroy_node(self):
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = KernelLogMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
