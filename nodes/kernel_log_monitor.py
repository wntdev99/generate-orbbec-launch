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
from rclpy.executors import ExternalShutdownException

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
        self.declare_parameter('diag_period_sec', 5.0)     # /diagnostics summary interval
        self.declare_parameter('frame_id', '')

        self._keywords = [k.lower() for k in self.get_parameter('keywords').value if k]
        self._max_priority = max(0, min(7, int(self.get_parameter('max_priority').value)))
        self._backlog_lines = max(0, int(self.get_parameter('backlog_lines').value))
        self._frame_id = self.get_parameter('frame_id').value
        self._backlog = bool(self.get_parameter('include_backlog').value)
        diag_period = float(self.get_parameter('diag_period_sec').value)
        if diag_period <= 0.0:
            diag_period = 5.0

        self._pub = self.create_publisher(KernelLogEntry, '~/kernel_log', 50)
        self._diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)

        # rolling state for the diagnostic summary
        self._lock = threading.Lock()
        self._counts = {'err': 0, 'warn': 0, 'info': 0}
        self._last_message = ''
        self._worst = DiagnosticStatus.OK

        self._proc = None
        self._stop = threading.Event()

        self.create_timer(diag_period, self._publish_diagnostics)

        # The reader runs journalctl and auto-reconnects with backoff if the
        # stream ends, so a journald restart or transient error doesn't stop
        # monitoring permanently.
        self._reader = threading.Thread(target=self._run_journalctl_loop, daemon=True)
        self._reader.start()
        self.get_logger().info(
            f'kernel_log_monitor up: keywords={self._keywords}, '
            f'max_priority={self._max_priority}, backlog={self._backlog}')

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

    def _run_journalctl_loop(self):
        """Follow journalctl, reconnecting with exponential backoff on failure."""
        backoff = 1.0
        use_backlog = self._backlog  # only emit backlog on the first connection
        while not self._stop.is_set():
            if not self._start_journalctl(use_backlog):
                if shutil.which('journalctl') is None:
                    return  # missing binary -> never going to work, give up
                self._stop.wait(backoff)
                backoff = min(backoff * 2.0, 30.0)
                continue
            use_backlog = False

            got_data = False
            try:
                for line in self._proc.stdout:
                    if self._stop.is_set():
                        break
                    got_data = True
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._handle(entry)
            except Exception as exc:  # never let the reader thread die silently
                self.get_logger().warn(f'kernel log reader error: {exc}')

            err = self._cleanup_proc()
            if self._stop.is_set():
                break
            if got_data:
                backoff = 1.0  # the connection was healthy; reconnect promptly
            msg = err or ('journalctl stream ended; check that the user is in the '
                          'adm or systemd-journal group')
            self.get_logger().warn(f'{msg} (reconnecting in {backoff:.0f}s)')
            self._set_unavailable(msg)
            self._stop.wait(backoff)
            backoff = min(backoff * 2.0, 30.0)

    def _cleanup_proc(self):
        """Terminate the journalctl process and return any stderr text."""
        proc = self._proc
        self._proc = None
        if proc is None:
            return ''
        err = ''
        # Only read stderr when the process already exited (stream ended),
        # otherwise the read would block; on shutdown we skip it.
        if not self._stop.is_set() and proc.poll() is not None and proc.stderr is not None:
            try:
                err = (proc.stderr.read() or '').strip()
            except Exception:
                pass
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        return err

    def _handle(self, entry):
        if self._stop.is_set() or not rclpy.ok():
            return
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
        # Timer callback: never let it raise (a raising callback stops the executor).
        if self._stop.is_set() or not rclpy.ok():
            return
        try:
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
        except Exception as exc:
            self.get_logger().warn(f'diagnostics publish failed: {exc}')

    def destroy_node(self):
        self._stop.set()
        self._cleanup_proc()
        reader = getattr(self, '_reader', None)
        if reader is not None:
            reader.join(timeout=3.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = KernelLogMonitor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
