#!/usr/bin/env python3
"""Publish the set of Orbbec USB cameras currently present on the USB bus.

Reads sysfs (/sys/bus/usb/devices) -- no root required -- and publishes:
  * <node>/devices  (generate_orbbec_launch/OrbbecUsbDeviceArray, latched)
  * /diagnostics    (diagnostic_msgs/DiagnosticArray)

Hotplug events are reflected immediately via pyudev when it is available;
otherwise the node falls back to periodic polling only.

The key diagnostic value: a Gemini 330 is a USB3 camera. If it negotiates a
USB2 link (speed 480 Mbps) -- wrong port or a poor cable -- depth/color
streams can fail. This node surfaces that as a WARN so the cause is obvious.
"""

import os
import threading

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile,
    QoSDurabilityPolicy,
    QoSReliabilityPolicy,
    QoSHistoryPolicy,
)

from std_msgs.msg import Header
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from generate_orbbec_launch.msg import OrbbecUsbDevice, OrbbecUsbDeviceArray

SYSFS_USB = '/sys/bus/usb/devices'

# sysfs "speed" (Mbit/s) -> human-readable USB generation
_SPEED_TABLE = {
    1: 'USB 1.0 (Low-Speed 1.5 Mbps)',
    2: 'USB 1.0 (Low-Speed 1.5 Mbps)',
    12: 'USB 1.1 (Full-Speed 12 Mbps)',
    480: 'USB 2.0 (High-Speed 480 Mbps)',
    5000: 'USB 3.2 Gen1 (5 Gbps)',
    10000: 'USB 3.2 Gen2 (10 Gbps)',
    20000: 'USB 3.2 Gen2x2 / USB4 (20 Gbps)',
}


def _read(path):
    """Read a sysfs attribute, returning '' on any error."""
    try:
        with open(path, 'r') as handle:
            return handle.read().strip()
    except OSError:
        return ''


def usb_generation(speed_mbps):
    return _SPEED_TABLE.get(speed_mbps, f'unknown ({speed_mbps} Mbps)')


class UsbCameraMonitor(Node):
    def __init__(self):
        super().__init__('usb_camera_monitor')

        self.declare_parameter('poll_period_sec', 2.0)
        self.declare_parameter('vendor_ids', ['2bc5'])
        self.declare_parameter('expected_serials', [''])  # empty -> no expectation
        self.declare_parameter('frame_id', '')

        self._vendor_ids = {v.lower() for v in self.get_parameter('vendor_ids').value}
        self._expected = [s for s in self.get_parameter('expected_serials').value if s]
        self._frame_id = self.get_parameter('frame_id').value
        period = float(self.get_parameter('poll_period_sec').value)

        latched = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
        )
        self._dev_pub = self.create_publisher(OrbbecUsbDeviceArray, '~/devices', latched)
        self._diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)

        self._lock = threading.Lock()
        self._timer = self.create_timer(period, self.scan_and_publish)
        self._udev_observer = self._start_udev_observer()

        mode = 'pyudev hotplug + polling' if self._udev_observer else \
            'polling only (pyudev unavailable)'
        self.get_logger().info(
            f'usb_camera_monitor up: vendors={sorted(self._vendor_ids)}, '
            f'period={period}s, mode={mode}')
        self.scan_and_publish()  # publish an initial snapshot right away

    def _start_udev_observer(self):
        try:
            import pyudev
        except ImportError:
            return None
        try:
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by('usb')

            def handler(action, device):  # noqa: ARG001 - signature fixed by pyudev
                self.scan_and_publish()

            observer = pyudev.MonitorObserver(monitor, handler)
            observer.start()
            return observer
        except Exception as exc:  # defensive: never let monitoring setup kill the node
            self.get_logger().warn(f'pyudev observer failed ({exc}); polling only')
            return None

    def scan(self):
        """Return a list of OrbbecUsbDevice for every matching USB device."""
        devices = []
        seen = set()
        try:
            entries = sorted(os.listdir(SYSFS_USB))
        except OSError:
            return devices
        for name in entries:
            base = os.path.join(SYSFS_USB, name)
            vid = _read(os.path.join(base, 'idVendor')).lower()
            if not vid or vid not in self._vendor_ids:
                continue
            serial = _read(os.path.join(base, 'serial'))
            key = serial or name
            if key in seen:  # a device can expose multiple sysfs nodes
                continue
            seen.add(key)

            speed_raw = _read(os.path.join(base, 'speed'))
            try:
                speed = int(round(float(speed_raw))) if speed_raw else 0
            except ValueError:
                speed = 0

            dev = OrbbecUsbDevice()
            dev.serial = serial
            dev.product = _read(os.path.join(base, 'product'))
            dev.usb_port = name
            dev.device_path = base
            dev.id_vendor = vid
            dev.id_product = _read(os.path.join(base, 'idProduct')).lower()
            dev.speed_mbps = speed
            dev.usb_generation = usb_generation(speed)
            dev.bcd_usb = _read(os.path.join(base, 'version'))
            dev.below_usb3 = 0 < speed < 5000
            devices.append(dev)
        return devices

    def scan_and_publish(self):
        with self._lock:
            devices = self.scan()
            now = self.get_clock().now().to_msg()

            arr = OrbbecUsbDeviceArray()
            arr.header = Header(stamp=now, frame_id=self._frame_id)
            arr.count = len(devices)
            arr.devices = devices
            self._dev_pub.publish(arr)
            self._diag_pub.publish(self._build_diagnostics(devices, now))

    def _build_diagnostics(self, devices, stamp):
        diag = DiagnosticArray()
        diag.header.stamp = stamp

        found_serials = {d.serial for d in devices if d.serial}
        summary = DiagnosticStatus()
        summary.name = 'orbbec_usb: summary'
        summary.hardware_id = 'orbbec_usb'
        summary.level = DiagnosticStatus.OK
        summary.message = f'{len(devices)} Orbbec camera(s) detected'
        summary.values.append(KeyValue(key='count', value=str(len(devices))))
        if self._expected:
            summary.values.append(KeyValue(key='expected', value=str(len(self._expected))))
            missing = [s for s in self._expected if s not in found_serials]
            if missing:
                summary.level = DiagnosticStatus.ERROR
                summary.message = f'{len(devices)} detected; missing {len(missing)} expected'
                summary.values.append(KeyValue(key='missing_serials', value=','.join(missing)))
        diag.status.append(summary)

        for dev in devices:
            status = DiagnosticStatus()
            label = dev.serial or dev.usb_port
            status.name = f'orbbec_usb: {label}'
            status.hardware_id = dev.serial or dev.usb_port
            if dev.below_usb3:
                status.level = DiagnosticStatus.WARN
                status.message = (
                    f'running at {dev.usb_generation} - USB3 expected; '
                    'depth/color may fail')
            else:
                status.level = DiagnosticStatus.OK
                status.message = dev.usb_generation
            status.values = [
                KeyValue(key='serial', value=dev.serial),
                KeyValue(key='product', value=dev.product),
                KeyValue(key='usb_port', value=dev.usb_port),
                KeyValue(key='speed_mbps', value=str(dev.speed_mbps)),
                KeyValue(key='usb_generation', value=dev.usb_generation),
                KeyValue(key='bcd_usb', value=dev.bcd_usb),
                KeyValue(key='id_product', value=dev.id_product),
            ]
            diag.status.append(status)
        return diag


def main(args=None):
    rclpy.init(args=args)
    node = UsbCameraMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node._udev_observer is not None:
            try:
                node._udev_observer.stop()
            except Exception:
                pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
