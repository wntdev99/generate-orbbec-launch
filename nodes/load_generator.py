#!/usr/bin/env python3
"""Service-controlled traffic / middleware load generator.

One node, four engines, three reachable scopes -- all driven by a ROS service:

  engines (StartLoad.mode):
    * ros_pub : publish a large payload at high rate on ~/load_topic. RMW-agnostic,
                so the *same* job stresses Fast DDS or Zenoh depending on the active
                RMW_IMPLEMENTATION. This is the ROS2/Zenoh middleware test.
    * tcp     : open N TCP sockets to target:port and blast a buffer. Needs a
                listener (run load_sink on the peer, or any TCP sink / iperf3 -s).
    * udp     : fire UDP datagrams at target:port. Fire-and-forget -- it generates
                real egress even with no listener (packets are dropped downstream),
                so it saturates the PC<->gateway link and the WAN uplink directly.
    * iperf3  : wrap the iperf3 client for accurate, industry-standard measurement.
                Needs `iperf3 -s` at the target (or a public iperf3 server).

  scope (StartLoad.target keyword -> resolved host):
    * 'gateway'  -> default-route gateway IP        (PC <-> router link, scope (1))
    * 'internal' -> configured LAN peer             (intra-LAN, scope (2))
    * 'internet' -> configured public target        (WAN uplink, scope (3))
    * anything else is used as a literal host/IP.

Safety: jobs are capped at `max_duration_sec` and `max_rate_mbps`. An unlimited
"max blast" (rate_mbps=0) is refused unless the request sets allow_unlimited=true.

Services:
  * ~/start (generate_orbbec_launch/StartLoad) -- start one job (one at a time)
  * ~/stop  (std_srvs/Trigger)                 -- stop the running job
Publishes:
  * ~/stats (generate_orbbec_launch/LoadStats) -- live tx/rx rate + totals
  * ~/load_topic (std_msgs/UInt8MultiArray)    -- the ros_pub payload stream
"""

import re
import socket
import subprocess
import threading
import time
import json

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from std_msgs.msg import Header, UInt8MultiArray
from std_srvs.srv import Trigger
from generate_orbbec_launch.msg import LoadStats
from generate_orbbec_launch.srv import StartLoad

_GW_RE = re.compile(r'default\s+via\s+(\S+)')
_VALID_MODES = ('ros_pub', 'tcp', 'udp', 'iperf3')


def default_gateway():
    """Default-route gateway IP, or None."""
    try:
        out = subprocess.run(['ip', 'route', 'show', 'default'],
                             capture_output=True, text=True, timeout=3.0).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _GW_RE.search(out)
    return m.group(1) if m else None


class _Pacer:
    """Crude byte-rate limiter. bytes_per_sec <= 0 means unlimited."""

    def __init__(self, bytes_per_sec):
        self.bps = float(bytes_per_sec)
        self._start = time.monotonic()
        self._sent = 0

    def consume(self, n, stop):
        self._sent += n
        if self.bps <= 0.0:
            return
        target = self._start + self._sent / self.bps
        delay = target - time.monotonic()
        if delay > 0.0:
            stop.wait(min(delay, 0.2))


class _Job:
    """Bookkeeping for one running load job."""

    def __init__(self, job_id, mode, target, parallel, deadline):
        self.id = job_id
        self.mode = mode
        self.target = target          # resolved host/ip, or 'ros_topic'
        self.parallel = parallel
        self.deadline = deadline      # monotonic time to stop at
        self.stop = threading.Event()
        self.threads = []
        # per-worker counters (GIL keeps int +=/reads atomic enough for stats)
        self.tx = [0] * parallel
        self.msgs = [0] * parallel
        self.err = [0] * parallel
        self.detail = ''
        self.publisher = None
        self.payload_bytes = 0
        self.publish_hz = 0.0

    def totals(self):
        return sum(self.tx), sum(self.msgs), sum(self.err)


class LoadGenerator(Node):
    def __init__(self):
        super().__init__('load_generator')

        # scope resolution
        self.declare_parameter('internal_peer', '')      # LAN peer (run load_sink there)
        self.declare_parameter('internet_target', '8.8.8.8')
        # engine defaults
        self.declare_parameter('default_port', 5201)     # iperf3 default
        self.declare_parameter('default_duration_sec', 30.0)
        self.declare_parameter('default_parallel', 4)
        self.declare_parameter('default_publish_hz', 100.0)
        self.declare_parameter('ros_payload_bytes', 65000)
        self.declare_parameter('udp_payload_bytes', 1400)  # <= typical MTU
        self.declare_parameter('tcp_buffer_bytes', 65536)
        # safety caps
        self.declare_parameter('max_duration_sec', 300.0)  # 0 = no cap
        self.declare_parameter('max_rate_mbps', 1000.0)    # 0 = no cap
        # ros_pub QoS
        self.declare_parameter('ros_qos_depth', 10)
        self.declare_parameter('ros_reliable', True)
        # misc
        self.declare_parameter('iperf3_path', 'iperf3')
        self.declare_parameter('stats_period_sec', 1.0)
        self.declare_parameter('frame_id', '')

        self._internal_peer = self.get_parameter('internal_peer').value
        self._internet_target = self.get_parameter('internet_target').value
        self._default_port = int(self.get_parameter('default_port').value)
        self._default_duration = float(self.get_parameter('default_duration_sec').value)
        self._default_parallel = max(1, int(self.get_parameter('default_parallel').value))
        self._default_hz = float(self.get_parameter('default_publish_hz').value)
        self._ros_payload = int(self.get_parameter('ros_payload_bytes').value)
        self._udp_payload = int(self.get_parameter('udp_payload_bytes').value)
        self._tcp_buf = int(self.get_parameter('tcp_buffer_bytes').value)
        self._max_duration = float(self.get_parameter('max_duration_sec').value)
        self._max_rate = float(self.get_parameter('max_rate_mbps').value)
        self._qos_depth = int(self.get_parameter('ros_qos_depth').value)
        self._reliable = bool(self.get_parameter('ros_reliable').value)
        self._iperf3 = self.get_parameter('iperf3_path').value
        self._frame_id = self.get_parameter('frame_id').value
        stats_period = float(self.get_parameter('stats_period_sec').value) or 1.0

        self._lock = threading.Lock()
        self._job = None
        self._job_seq = 0
        self._prev_tx = 0          # last sampled cumulative bytes (for bps)
        self._prev_t = time.monotonic()

        self._pub = self.create_publisher(LoadStats, '~/stats', 10)
        self._start_srv = self.create_service(StartLoad, '~/start', self._on_start)
        self._stop_srv = self.create_service(Trigger, '~/stop', self._on_stop)
        self._timer = self.create_timer(stats_period, self._tick)

        self.get_logger().info(
            'load_generator up: call ~/start (StartLoad) to begin, ~/stop (Trigger) to halt. '
            f'caps: max_duration={self._max_duration}s, max_rate={self._max_rate}Mbps')

    # ---- target resolution -------------------------------------------------

    def _resolve_target(self, mode, target):
        """Return (host, error). host is 'ros_topic' for ros_pub."""
        if mode == 'ros_pub':
            return 'ros_topic', None
        key = (target or '').strip()
        low = key.lower()
        if low == 'gateway':
            gw = default_gateway()
            return (gw, None) if gw else (None, 'no default gateway found')
        if low == 'internal':
            if not self._internal_peer:
                return None, "scope 'internal' needs the internal_peer parameter set"
            return self._internal_peer, None
        if low == 'internet':
            return self._internet_target, None
        if not key:
            return None, 'target is required for network modes'
        return key, None

    # ---- service: start ----------------------------------------------------

    def _on_start(self, req, resp):
        mode = (req.mode or '').strip().lower()
        if mode not in _VALID_MODES:
            resp.accepted = False
            resp.message = f"unknown mode '{req.mode}'; use one of {_VALID_MODES}"
            return resp

        with self._lock:
            if self._job is not None and not self._job.stop.is_set():
                resp.accepted = False
                resp.message = f"job '{self._job.id}' is running; call ~/stop first"
                return resp

            host, err = self._resolve_target(mode, req.target)
            if err:
                resp.accepted = False
                resp.message = err
                return resp

            # --- rate (with safety cap) ---
            # ros_pub is timer-paced (publish_hz x payload), so it is inherently
            # bounded -- never an unbounded blast. Its effective rate is clamped to
            # max_rate_mbps inside _spawn_ros_pub, so no allow_unlimited is needed.
            # Socket modes with rate_mbps=0 ARE unbounded and require an explicit opt-in.
            rate = float(req.rate_mbps)
            note = []
            if mode != 'ros_pub':
                if rate <= 0.0:
                    if not req.allow_unlimited:
                        resp.accepted = False
                        resp.message = ('rate_mbps=0 (max blast) refused; '
                                        'set allow_unlimited=true to override the safety cap')
                        return resp
                    note.append('unlimited rate')
                elif self._max_rate > 0.0 and rate > self._max_rate:
                    note.append(f'rate capped {rate}->{self._max_rate} Mbps')
                    rate = self._max_rate

            # --- duration (with safety cap) ---
            dur = float(req.duration_sec) or self._default_duration
            if self._max_duration > 0.0 and dur > self._max_duration:
                note.append(f'duration capped {dur}->{self._max_duration}s')
                dur = self._max_duration

            parallel = int(req.parallel) or self._default_parallel
            parallel = max(1, parallel)
            if mode == 'ros_pub':
                parallel = 1  # single publisher; scale via hz/payload instead
            port = int(req.port) or self._default_port

            self._job_seq += 1
            job_id = f'{mode}-{self._job_seq}'
            deadline = time.monotonic() + dur
            job = _Job(job_id, mode, host, parallel, deadline)

            rate_bps_total = rate * 1e6 / 8.0 if rate > 0.0 else 0.0

            try:
                if mode == 'ros_pub':
                    self._spawn_ros_pub(job, req, rate_bps_total)
                elif mode == 'tcp':
                    self._spawn_tcp(job, host, port, rate_bps_total)
                elif mode == 'udp':
                    self._spawn_udp(job, req, host, port, rate_bps_total)
                elif mode == 'iperf3':
                    self._spawn_iperf3(job, host, port, parallel, dur, rate, req)
            except Exception as exc:  # noqa: BLE001 - report any setup failure
                resp.accepted = False
                resp.message = f'failed to start: {exc}'
                return resp

            self._job = job
            self._prev_tx = 0
            self._prev_t = time.monotonic()

        msg = f"started '{job_id}' -> {host} ({mode}, {parallel}x, {dur:.0f}s)"
        if note:
            msg += ' [' + '; '.join(note) + ']'
        self.get_logger().info(msg)
        resp.accepted = True
        resp.message = msg
        resp.job_id = job_id
        resp.resolved_target = host
        return resp

    # ---- engines -----------------------------------------------------------

    def _spawn_ros_pub(self, job, req, rate_bps_total):
        payload = int(req.payload_bytes) or self._ros_payload
        hz = float(req.publish_hz) or self._default_hz
        if rate_bps_total > 0.0 and payload > 0:
            hz = max(1.0, rate_bps_total / payload)  # derive hz from requested rate
        # Safety: hard-clamp the effective rate (hz x payload) to max_rate_mbps so
        # ros_pub honors the same ceiling as the socket engines.
        if self._max_rate > 0.0 and payload > 0:
            max_bps = self._max_rate * 1e6 / 8.0
            if payload * hz > max_bps:
                hz = max(1.0, max_bps / payload)
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST, depth=self._qos_depth,
            reliability=(ReliabilityPolicy.RELIABLE if self._reliable
                         else ReliabilityPolicy.BEST_EFFORT))
        job.publisher = self.create_publisher(UInt8MultiArray, '~/load_topic', qos)
        job.payload_bytes = payload
        job.publish_hz = hz
        job.detail = f'{hz:.0f} Hz x {payload} B over RMW'
        t = threading.Thread(target=self._ros_pub_worker, args=(job, payload, hz), daemon=True)
        job.threads.append(t)
        t.start()

    def _ros_pub_worker(self, job, payload_bytes, hz):
        msg = UInt8MultiArray()
        msg.data = bytes(payload_bytes)
        interval = 1.0 / hz if hz > 0 else 0.0
        next_t = time.monotonic()
        while not job.stop.is_set() and time.monotonic() < job.deadline:
            try:
                job.publisher.publish(msg)
                job.tx[0] += payload_bytes
                job.msgs[0] += 1
            except Exception:  # noqa: BLE001
                job.err[0] += 1
            if interval:
                next_t += interval
                delay = next_t - time.monotonic()
                if delay > 0:
                    job.stop.wait(delay)
                else:
                    next_t = time.monotonic()
        job.stop.set()

    def _spawn_tcp(self, job, host, port, rate_bps_total):
        per = rate_bps_total / job.parallel if rate_bps_total > 0 else 0.0
        job.detail = f'tcp -> {host}:{port}'
        for idx in range(job.parallel):
            t = threading.Thread(target=self._tcp_worker,
                                  args=(job, idx, host, port, per), daemon=True)
            job.threads.append(t)
            t.start()

    def _tcp_worker(self, job, idx, host, port, per_bps):
        buf = bytes(self._tcp_buf)
        pacer = _Pacer(per_bps)
        while not job.stop.is_set() and time.monotonic() < job.deadline:
            try:
                with socket.create_connection((host, port), timeout=5.0) as s:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    while not job.stop.is_set() and time.monotonic() < job.deadline:
                        n = s.send(buf)
                        job.tx[idx] += n
                        job.msgs[idx] += 1
                        pacer.consume(n, job.stop)
            except OSError as exc:
                job.err[idx] += 1
                job.detail = f'tcp {host}:{port}: {exc}'
                job.stop.wait(0.5)  # back off then retry until deadline

    def _spawn_udp(self, job, req, host, port, rate_bps_total):
        payload = int(req.payload_bytes) or self._udp_payload
        per = rate_bps_total / job.parallel if rate_bps_total > 0 else 0.0
        job.payload_bytes = payload
        job.detail = f'udp -> {host}:{port} x {payload} B'
        for idx in range(job.parallel):
            t = threading.Thread(target=self._udp_worker,
                                 args=(job, idx, host, port, payload, per), daemon=True)
            job.threads.append(t)
            t.start()

    def _udp_worker(self, job, idx, host, port, payload_bytes, per_bps):
        payload = bytes(payload_bytes)
        pacer = _Pacer(per_bps)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError as exc:
            job.err[idx] += 1
            job.detail = f'udp socket: {exc}'
            return
        try:
            dest = (host, port)
            while not job.stop.is_set() and time.monotonic() < job.deadline:
                try:
                    n = sock.sendto(payload, dest)
                    job.tx[idx] += n
                    job.msgs[idx] += 1
                except OSError:
                    job.err[idx] += 1
                    job.stop.wait(0.01)
                pacer.consume(payload_bytes, job.stop)
        finally:
            sock.close()

    def _spawn_iperf3(self, job, host, port, parallel, dur, rate, req):
        # iperf3 mode is TCP; for raw UDP blasting use mode 'udp' instead.
        cmd = [self._iperf3, '-c', host, '-p', str(port),
               '-t', str(int(max(1, dur))), '-P', str(parallel), '-J']
        if rate > 0.0:
            cmd += ['-b', f'{rate}M']
        elif req.allow_unlimited:
            cmd += ['-b', '0']
        job.detail = 'iperf3 running: ' + ' '.join(cmd[1:])
        t = threading.Thread(target=self._iperf3_worker, args=(job, cmd, dur), daemon=True)
        job.threads.append(t)
        t.start()

    def _iperf3_worker(self, job, cmd, dur):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=dur + 15.0)
        except FileNotFoundError:
            job.err[0] += 1
            job.detail = f'iperf3 not found ({self._iperf3}); apt install iperf3'
            job.stop.set()
            return
        except subprocess.TimeoutExpired:
            job.err[0] += 1
            job.detail = 'iperf3 timed out'
            job.stop.set()
            return
        try:
            data = json.loads(res.stdout)
            end = data.get('end', {})
            sent = end.get('sum_sent', {})
            bps = float(sent.get('bits_per_second', 0.0))
            byts = int(sent.get('bytes', 0))
            job.tx[0] = byts
            job.msgs[0] = 1
            job.detail = f'iperf3 done: {bps/1e6:.1f} Mbps, {byts/1e6:.1f} MB'
        except (ValueError, KeyError):
            err = (res.stderr or '').strip().splitlines()
            job.err[0] += 1
            job.detail = 'iperf3 error: ' + (err[-1] if err else 'unparseable output')
        job.stop.set()

    # ---- service: stop -----------------------------------------------------

    def _on_stop(self, _req, resp):
        with self._lock:
            job = self._job
        if job is None:
            resp.success = True
            resp.message = 'idle; nothing to stop'
            return resp
        self._finish_job(job)
        resp.success = True
        resp.message = f"stopped '{job.id}'"
        return resp

    def _finish_job(self, job):
        job.stop.set()
        for t in job.threads:
            t.join(timeout=6.0)
        if job.publisher is not None:
            self.destroy_publisher(job.publisher)
            job.publisher = None
        self.get_logger().info(
            f"job '{job.id}' ended: {job.totals()[1]} msgs, "
            f"{job.totals()[0]/1e6:.1f} MB, {job.totals()[2]} errors")

    # ---- stats tick --------------------------------------------------------

    def _tick(self):
        if not rclpy.ok():
            return
        with self._lock:
            job = self._job
            # reap a job whose deadline elapsed / workers finished
            if job is not None and job.stop.is_set() and all(
                    not t.is_alive() for t in job.threads):
                self._finish_job(job)
                self._job = None
                job = None

        now = time.monotonic()
        msg = LoadStats()
        msg.header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self._frame_id)
        if job is None:
            msg.mode = 'idle'
            msg.running = False
            self._prev_tx = 0
            self._prev_t = now
        else:
            tx, msgs, err = job.totals()
            dt = now - self._prev_t
            msg.tx_bps = max(0.0, (tx - self._prev_tx) / dt) if dt > 0 else 0.0
            self._prev_tx = tx
            self._prev_t = now
            msg.job_id = job.id
            msg.mode = job.mode
            msg.target = job.target
            msg.running = not job.stop.is_set()
            msg.bytes_total = tx
            msg.msgs_total = msgs
            msg.errors = err
            msg.detail = job.detail
        self._pub.publish(msg)

    def destroy_node(self):
        with self._lock:
            job = self._job
            self._job = None
        if job is not None:
            self._finish_job(job)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = LoadGenerator()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
