# generate_orbbec_launch

여러 대의 Orbbec Gemini 카메라를 실행하기 위한 **ROS 2 패키지**(`ament_cmake`, C++/Python
혼합 가능, 대상 배포판 **Jazzy**)입니다. 다음 기능을 제공합니다.

1. 연결된 Orbbec(VID `2bc5`) 카메라를 자동 탐지하고 대화형으로 이름·primary를 지정해 멀티
   카메라 런치 파일을 생성하는 **스크립트**(`scripts/generate_orbbec_launch.sh`).
2. USB 버스에 연결된 카메라 목록·포트·USB 세대를 토픽으로 발행하는 **모니터 노드**
   (`usb_camera_monitor`).
3. 카메라/USB 관련 커널 로그(dmesg)를 토픽으로 발행하는 **모니터 노드**
   (`kernel_log_monitor`).
4. 공유기 WiFi WAN(업링크) 신호 dBm을 토픽으로 발행하는 **모니터 노드**
   (`wifi_wan_monitor`) — 유선 연결 머신용.
5. 종단 latency와 끊김(지속 시간·횟수)을 토픽으로 발행하는 **모니터 노드**
   (`link_latency_monitor`).
6. 네트워크 인터페이스 사용량(rx/tx)을 토픽으로 발행하는 **모니터 노드**
   (`net_throughput_monitor`, 인터페이스 자동 감지).
7. 공유기 WAN/LAN 인터페이스 사용량(rx/tx)을 토픽으로 발행하는 **모니터 노드**
   (`router_throughput_monitor`, SSH).
8. 서비스로 트리거하는 **부하 발생 노드**(`load_generator`) + 수신 노드(`load_sink`) —
   ROS2/Zenoh 미들웨어 부하(`ros_pub`)와 네트워크 부하(`tcp`/`udp`/`iperf3`)를
   게이트웨이/내부/외부 인터넷 범위로 발생시켜 테스트합니다.

## 패키지 구조

```
generate_orbbec_launch/
├── package.xml                 # ament_cmake 패키지 매니페스트 (rosidl 메시지 생성 포함)
├── CMakeLists.txt              # 빌드/설치 규칙 (C++ 노드 추가 지점 주석으로 표시)
├── msg/
│   ├── OrbbecUsbDevice.msg      # USB 카메라 1대의 정보
│   ├── OrbbecUsbDeviceArray.msg # 탐지된 카메라 스냅샷
│   ├── KernelLogEntry.msg       # 커널 로그 1줄
│   ├── WifiWanStatus.msg        # 공유기 WiFi WAN 신호
│   ├── PingLatency.msg          # latency 샘플 1건
│   ├── LinkOutage.msg           # 끊김 1건(복구 시)
│   ├── NetThroughput.msg        # 인터페이스 throughput 1건
│   └── LoadStats.msg            # 부하 발생/수신 실시간 통계
├── srv/
│   └── StartLoad.srv            # load_generator 부하 작업 시작 요청
├── config/
│   └── monitors.yaml            # 노드 파라미터 (주기 등) 중앙 관리
├── launch/
│   ├── all.launch.py            # 모든 모니터 노드 한 번에 (기본 전부 ON, 그룹 토글)
│   ├── monitors.launch.py       # usb+kernel 모니터 함께 실행 (config 사용)
│   ├── wifi_wan_monitor.launch.py  # WiFi WAN 모니터 실행 (config 사용)
│   └── link_latency.launch.py   # latency internet+gateway 인스턴스 (config 사용)
├── nodes/
│   ├── usb_camera_monitor.py    # USB 카메라 인벤토리 모니터 노드 (rclpy)
│   ├── kernel_log_monitor.py    # 커널 로그(dmesg) 모니터 노드 (rclpy)
│   ├── wifi_wan_monitor.py      # 공유기 WiFi WAN 신호 모니터 노드 (rclpy)
│   ├── link_latency_monitor.py  # 종단 latency/끊김 모니터 노드 (rclpy)
│   ├── net_throughput_monitor.py # 호스트 네트워크 사용량(rx/tx) 모니터 노드 (rclpy)
│   ├── router_throughput_monitor.py # 공유기 WAN/LAN 사용량 모니터 노드 (rclpy, SSH)
│   ├── load_generator.py       # 서비스 제어 부하 발생 노드 (ros_pub/tcp/udp/iperf3)
│   └── load_sink.py            # 부하 수신 노드 (tcp/udp 싱크 + ROS 구독)
└── scripts/
    ├── setup.sh                    # 의존성 설치 + colcon 빌드 (+선택: 라우터 SSH 키)
    └── generate_orbbec_launch.sh   # 런치 파일 생성 스크립트 (ROS 노드가 아닌 순수 스크립트)
```

## 설치 / 빌드

워크스페이스 `src/` 아래에 둔 뒤 setup 스크립트로 한 번에 처리할 수 있습니다.

```bash
cd <workspace>/src/generate_orbbec_launch
./scripts/setup.sh                 # 의존성 설치(rosdep + ethtool/pyudev) + colcon 빌드
./scripts/setup.sh --no-deps       # 빌드만
./scripts/setup.sh --wifi-key      # 추가로 wifi_wan_monitor용 라우터 SSH 키 설정(비번 1회 입력)
```

스크립트는 자신의 위치(`<ws>/src/<pkg>/scripts`)에서 워크스페이스 루트를 자동 감지해 거기서
`colcon build --packages-select generate_orbbec_launch`를 실행합니다. 수동으로 하려면:

```bash
cd <workspace>
colcon build --packages-select generate_orbbec_launch
source install/setup.bash
```

## 설정 (`config/monitors.yaml`)

모니터 노드들의 파라미터(특히 **주기**)는 `config/monitors.yaml`에서 한곳에 관리합니다.
launch 파일들이 이 파일을 읽어 적용합니다(노드별 섹션, 한 파일 공유).

| 노드 | 주기 파라미터 | 기본값 |
|---|---|---|
| `usb_camera_monitor` | `poll_period_sec` | **2.0초** (sysfs 스캔) |
| `kernel_log_monitor` | `diag_period_sec` | **5.0초** (진단 요약; 로그 자체는 실시간 follow) |
| `wifi_wan_monitor` | `poll_period_sec` | **15.0초** (공유기 SSH) |

YAML을 수정한 뒤 다시 빌드(설치)하거나, 다른 파일로 덮어쓸 수 있습니다:
```bash
ros2 launch generate_orbbec_launch monitors.launch.py config_file:=/path/to/your.yaml
```

## 모니터 실행 (launch)

모든 launch는 **하나의 공유 config**(`config/monitors.yaml`)를 읽습니다. 각 노드는 자기 이름과
일치하는 섹션만 가져가므로 한 파일을 공유해도 안전합니다.

```bash
# 전부 한 번에 (기본 모두 ON) -- 7개 노드
ros2 launch generate_orbbec_launch all.launch.py
ros2 launch generate_orbbec_launch all.launch.py enable_wifi_wan:=false enable_link_latency:=false

# 그룹별로 따로
ros2 launch generate_orbbec_launch monitors.launch.py          # usb + kernel
ros2 launch generate_orbbec_launch wifi_wan_monitor.launch.py  # WiFi WAN dBm
ros2 launch generate_orbbec_launch link_latency.launch.py      # latency internet + gateway
```

`all.launch.py`는 위 그룹 launch들을 묶어 실행하며, 토글: `enable_usb_monitor`,
`enable_kernel_monitor`, `enable_wifi_wan`, `enable_link_latency`, `enable_net_throughput`,
`enable_router_throughput` (모두 기본 `true`). 머신마다 필요한 것만 켜면 됩니다(예: 카메라
호스트는 usb+kernel, 유선 게이트웨이 머신은 wifi_wan+router_throughput+link_latency).
부하 발생 노드 `enable_load_generator` / `enable_load_sink`는 **트래픽을 능동적으로
밀어내므로 기본 `false`**입니다(필요 시 `enable_load_generator:=true`로 켭니다).

## 동작 방식

1. **자동 탐지** — `/sys/bus/usb/devices`를 훑어 VID `2bc5`인 장치를 모두 찾고, 각 장치의
   시리얼 번호와 USB 포트(busid)를 수집합니다. (중복 sysfs 노드는 시리얼 기준으로 제거)
2. **대화형 이름 지정** — 탐지된 카메라마다 시리얼·USB 포트를 보여주고 이름을 입력받습니다.
   빈 이름·중복 이름은 거부합니다.
3. **primary 선택** — 어느 카메라를 primary로 쓸지 인덱스로 고릅니다. primary는
   `software_triggering`, 나머지는 모두 `hardware_triggering`으로 설정됩니다.
4. **런치 파일 생성** — 카메라 대수(`device_num`)와 트리거 모드를 반영해 런치 파일을
   만듭니다. 동기화 안정성을 위해 secondary 카메라들이 먼저 올라온 뒤, primary 카메라는
   `TimerAction(period=3.0)`으로 3초 지연 후 마지막에 실행됩니다. 파일명은 모드에 따라
   달라집니다(아래 표 참고).

### 생성되는 파일명

| 실행 인자 | 출력 파일명 |
|---|---|
| (기본, 동기화) | `multi_camera_synced.launch.py` |
| `--no-sync` | `multi_camera_standalone.launch.py` |
| `--no-sync=free_run` | `multi_camera_free_run.launch.py` |

## 사용법

스크립트는 ROS 노드가 아니라 그대로 실행하는 순수 스크립트입니다. 생성된 런치 파일은
**패키지의 `launch/` 디렉터리에 자동 저장**되며(스크립트 위치 기준 `../launch`), 이후
`colcon build`로 설치됩니다.

```bash
cd scripts
./generate_orbbec_launch.sh                  # 동기화 구성 (primary/secondary)
./generate_orbbec_launch.sh --no-sync         # 비동기 구성 (기본 standalone)
./generate_orbbec_launch.sh --no-sync=free_run # 비동기 구성 (free_run)
./generate_orbbec_launch.sh --dry-run         # 가짜 장치 목록으로 흐름만 확인 (하드웨어 불필요)
./generate_orbbec_launch.sh --help            # 사용법 출력
```

### `--dry-run`

하드웨어가 연결되어 있지 않아도 전체 흐름(탐지 → 이름 지정 → primary 선택 → 파일 생성)을
점검할 수 있도록 고정된 가짜 장치 4대를 사용합니다. sysfs에 접근하지 않습니다. 생성된
런치 파일은 실제 하드웨어로 다시 검증한 뒤 사용하십시오.

### `--no-sync` (비동기 모드)

카메라들을 **서로 동기화할 필요가 없을 때** 사용합니다. 동기화 허브·트리거 케이블이 필요
없고, **primary 선택 단계와 `TimerAction` 지연이 생략**되며, 모든 카메라가 독립적으로 실행됩니다.

- `--no-sync` — 기본값 `standalone`. 장치끼리는 동기화하지 않지만, **한 카메라 안의
  Color·Depth는 동기화**됩니다(같은 프레임레이트 전제). 대부분의 비동기 용도에 권장됩니다.
- `--no-sync=free_run` — 장치 간 동기화 없음. Color·Depth를 **서로 다른 프레임레이트**로
  둘 수 있는 완전 자유 구동 모드입니다.

> `sync_mode` 문자열은 `orbbec_camera` 래퍼에서 대소문자 구분 없이 처리되며, 인식되지 않는
> 값은 `free_run`으로 폴백됩니다.

## 주의 사항

- **이름 규칙** — 카메라 이름은 ROS 2 규칙에 따라 영문자로 시작하고 영문자·숫자·밑줄(`_`)만
  사용할 수 있습니다. 규칙에 맞지 않으면 다시 입력을 요청합니다.
- **덮어쓰기** — `launch/`에 같은 이름의 런치 파일이 이미 있으면 덮어쓸지 먼저 확인합니다.
- **출력 위치** — 파일은 이 패키지의 `launch/` 디렉터리에 저장됩니다. 실행하려면
  `colcon build`로 워크스페이스를 다시 빌드해 런치 파일이 설치되도록 하십시오.
- **버전 관리** — 생성된 런치 파일은 호스트마다 USB 포트·시리얼이 달라 `.gitignore`에서
  제외(미추적)됩니다. 특정 런치 파일을 커밋하려면 `.gitignore` 규칙을 조정하십시오.

## 요구 사항

- Bash
- Linux (USB 장치 탐지에 `/sys/bus/usb/devices` 사용)
- ROS 2 Jazzy + `colcon` (패키지 빌드 시)
- `orbbec_camera` 패키지 (생성된 런치 파일 실행 시)
- `rclpy` (모니터 노드 실행 시), `python3-pyudev` (선택: 핫플러그 즉시 감지)

## 생성 결과 예시

`gemini_330_series.launch.py`를 카메라마다 include 하며, 각 카메라에 다음 인자를 주입합니다.

- `camera_name` — 사용자가 지정한 이름
- `usb_port` — 자동 탐지된 USB 포트
- `device_num` — 탐지된 카메라 총 대수
- `sync_mode` — 동기화 모드에서는 primary가 `software_triggering`, 그 외는
  `hardware_triggering`. 비동기(`--no-sync`) 모드에서는 모든 카메라가 `standalone`
  (또는 `free_run`)
- `config_file_path` — `orbbec_camera` 패키지의 `config/camera_params.yaml`

---

# `usb_camera_monitor` 노드

USB 버스에 연결된 Orbbec 카메라 목록을 토픽으로 발행하는 `rclpy` 노드입니다. `/sys/bus/usb/devices`를
읽으므로 **root 권한이 필요 없습니다.**

```bash
ros2 run generate_orbbec_launch usb_camera_monitor
```

## 발행 토픽

| 토픽 | 타입 | 설명 |
|---|---|---|
| `~/devices` | `generate_orbbec_launch/OrbbecUsbDeviceArray` | 탐지된 카메라 스냅샷 (latched: `transient_local`) |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | `rqt_robot_monitor`용 진단 (요약 + 카메라별 상태) |

각 카메라에 대해 시리얼·제품명·USB 포트·링크 속도(`speed_mbps`)·USB 세대(`usb_generation`)·
`bcd_usb`를 제공합니다.

## 연결/해제 카운팅

노드는 스캔 간 카메라 집합 변화를 추적해 **연결/해제 횟수**를 셉니다. **카운터는 노드(런치)
시작 시 0부터** 시작합니다.

- 시작 시점에 이미 붙어 있던 카메라 → baseline (`connect_count=0`)
- 이후 빠졌다 → `disconnect_count` 증가, 다시 붙으면 → `connect_count` 증가
- 시작 후 새로 나타난 카메라 → `connect_count=1`

각 `OrbbecUsbDevice`에 `connect_count`/`disconnect_count`가 담기고, `/diagnostics` 요약에는
`total_connects`/`total_disconnects`가, 그리고 **빠진 채로 있는 카메라**는 별도 **WARN**
상태("currently disconnected (connects N, disconnects M)")로 표면화됩니다. 전이가 일어날 때마다
로그도 남깁니다.

> 폴링(`poll_period_sec`) 사이의 매우 빠른 뽑았다-꽂기는 놓칠 수 있습니다. `pyudev`가 설치돼
> 있으면 핫플러그 이벤트로 즉시 스캔하므로 정확도가 올라갑니다.

## 제공 서비스

| 서비스 | 타입 | 설명 |
|---|---|---|
| `~/rescan` | `std_srvs/Trigger` | 폴링 주기를 기다리지 않고 **즉시 재스캔**하여 토픽을 갱신. 응답 메시지에 탐지 대수 포함 |

```bash
ros2 service call /usb_camera_monitor/rescan std_srvs/srv/Trigger
# -> success=True, message='rescanned: N Orbbec camera(s) detected'
```

## 핵심 진단: USB2 강등 감지

Gemini 330은 USB3 카메라입니다. **USB2 포트나 저급 케이블에 꽂혀 링크가 480 Mbps로 떨어지면**
대역폭 부족으로 depth/color 스트림이 실패할 수 있습니다. 노드는 이 경우(`below_usb3=true`)를
diagnostic **WARN**으로 표면화합니다.

```
orbbec_usb: <serial>  WARN  running at USB 2.0 (High-Speed 480 Mbps) - USB3 expected; depth/color may fail
```

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `poll_period_sec` | `2.0` | sysfs 폴링 주기(초) |
| `vendor_ids` | `['2bc5']` | 탐지할 USB VID 목록 |
| `expected_serials` | `[]` | 기대 시리얼. 누락 시 요약 진단을 **ERROR**로 발행 |
| `frame_id` | `''` | 메시지 헤더 frame_id |

## 핫플러그(pyudev) — 선택 사항

`pyudev`가 설치돼 있으면 USB 연결/해제 이벤트에 **즉시** 반응해 토픽을 갱신합니다. 없으면
폴링만으로 동작합니다(시작 로그에 모드 표시).

```bash
sudo apt install python3-pyudev   # 핫플러그 즉시 감지를 원할 때
```

> **검증 완료**: ROS 2 Jazzy에서 `colcon build` 후, 실제 USB 장치로 `~/devices`·`/diagnostics`
> 발행, USB2 장치의 `below_usb3=true`/WARN, `expected_serials` 누락 시 요약 ERROR까지 확인했습니다.

---

# `kernel_log_monitor` 노드

카메라/USB 관련 **커널 로그(dmesg)** 라인을 토픽으로 발행하는 `rclpy` 노드입니다.

```bash
ros2 run generate_orbbec_launch kernel_log_monitor
```

## 권한 — root 불필요 (단, 그룹 필요)

Ubuntu는 `kernel.dmesg_restrict=1`이 기본이라 `dmesg`/`/dev/kmsg` 직접 읽기는 root/`CAP_SYSLOG`가
필요합니다. 이 노드는 대신 **systemd 저널의 커널 스트림**(`journalctl -k -f`)을 따라가므로,
실행 사용자가 **`adm` 또는 `systemd-journal` 그룹**에 속해 있으면 **root 없이** 동작합니다.

```bash
groups | grep -E 'adm|systemd-journal'   # 둘 중 하나에 속해 있어야 함
```

그룹에 없거나 `journalctl`이 없으면 노드는 살아 있되 `/diagnostics`에 **ERROR**로 사유를 보고합니다.

## 발행 토픽

| 토픽 | 타입 | 설명 |
|---|---|---|
| `~/kernel_log` | `generate_orbbec_launch/KernelLogEntry` | 매칭된 커널 로그 라인 (우선순위·메시지·매칭 키워드) |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | 누적 err/warn/info 카운트 + 마지막 메시지 요약 |

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `keywords` | `['usb','uvcvideo','xhci','orbbec','2bc5']` | 대소문자 무시 부분 일치 필터 |
| `max_priority` | `7` | 이 값 이하 우선순위만 발행 (예: `4`면 warning 이상만) |
| `include_backlog` | `false` | 시작 시 최근 로그도 방출할지 |
| `backlog_lines` | `50` | `include_backlog` 시 방출할 최근 커널 라인 수 |
| `frame_id` | `''` | 메시지 헤더 frame_id |

> **검증 완료**: FastDDS(localhost)로 빌드·실행 후, 최근 커널 로그에 실재하는 키워드로
> `~/kernel_log` 발행과 진단 카운트(info_count=9, 마지막 메시지 텍스트)까지 확인했습니다.
> (로컬 테스트는 zenoh 충돌 방지를 위해 `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`로 수행)

---

# `wifi_wan_monitor` 노드 (유선 머신용)

**유선으로 공유기에 연결된 머신**은 자기 NIC에 dBm이 없습니다. 하지만 인터넷 경로의 무선
구간 = **공유기의 WiFi WAN(업링크)** 가 있습니다. 이 노드는 그 업링크 신호를 공유기에서
SSH로 읽어(`iwinfo <iface> info`) 토픽으로 발행합니다.

```bash
ros2 run generate_orbbec_launch wifi_wan_monitor \
  --ros-args -p router_host:=192.168.34.1 -p wan_iface:=sta1
```

## 끊김/연결 판단 — `reachable` vs `associated`

- **`reachable`** = 공유기에 SSH 질의(iwinfo)가 성공했는가. 모니터링 경로의 성공 여부일 뿐,
  WiFi WAN 링크 상태가 아닙니다.
- **`associated`** = WiFi WAN이 실제로 외부 AP에 붙어 있는가(유효한 ESSID/신호 존재).
  업링크가 끊기면 `reachable=true`라도 `associated=false`가 됩니다.

따라서 **"무선 연결됨"** 은 `reachable && associated`로 판단하십시오. `/diagnostics`는
도달 불가 → **ERROR**, 도달했지만 미연결 → **ERROR("WiFi WAN down")**, 연결됨 → 신호
세기로 OK/WARN/ERROR로 보고합니다. (신호 0 dBm을 OK로 오판하던 문제도 이로써 해결됩니다.)

## 인증 — 비밀번호 저장 안 함 (SSH 키 필수)

`ssh -o BatchMode=yes`(키 기반)로만 접속합니다. 코드/설정에 **비밀번호를 저장하지 않습니다.**
먼저 이 머신 → 공유기로 키를 깔아두세요:
```bash
ssh-keygen -t ed25519
ssh-copy-id root@192.168.34.1
```
최소 권한을 원하면 공유기 `authorized_keys`에서 그 키를 `command="iwinfo ..."` 로 제한하세요.
키가 없거나 도달 실패면 노드는 살아 있되 `/diagnostics`에 **ERROR**로 사유를 보고합니다.

## 발행 토픽 / 파라미터

| 토픽 | 타입 |
|---|---|
| `~/wifi_wan` | `generate_orbbec_launch/WifiWanStatus` (reachable, **associated**, essid, signal_dbm, noise_dbm, quality, bitrate) |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` (신호 세기로 OK/WARN/ERROR) |

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `router_host` | `192.168.34.1` | 공유기 주소 |
| `router_user` | `root` | SSH 사용자 |
| `wan_iface` | `sta1` | WiFi WAN 인터페이스(iwinfo 이름) |
| `poll_period_sec` | `15.0` | 폴링 주기(공유기를 매번 SSH하므로 길게 권장) |
| `weak_warn_dbm` / `weak_error_dbm` | `-70` / `-80` | 약신호 경보 임계 |

> **검증 완료**: 빌드 통과, 노드 정상 spin/발행(크래시 없음), 그리고 파서를 실측 `iwinfo`
> 출력(ESSID "WATT", **-46 dBm**, 94/94, 1083 Mbit/s)으로 결정적 검증했습니다. 라이브
> 성공 경로는 대상 머신(james)→공유기 SSH 키 설정 후 동작합니다.

---

# 두 모니터 함께 실행 — `monitors.launch.py`

`usb_camera_monitor`와 `kernel_log_monitor`를 한 번에 띄우는 launch 파일입니다.

```bash
ros2 launch generate_orbbec_launch monitors.launch.py
ros2 launch generate_orbbec_launch monitors.launch.py enable_kernel_monitor:=false
ros2 launch generate_orbbec_launch monitors.launch.py kernel_max_priority:=4 kernel_include_backlog:=true
```

## Launch 인자

| 인자 | 기본값 | 설명 |
|---|---|---|
| `enable_usb_monitor` | `true` | `usb_camera_monitor` 실행 여부 |
| `enable_kernel_monitor` | `true` | `kernel_log_monitor` 실행 여부 |
| `usb_poll_period_sec` | `2.0` | USB 모니터 폴링 주기(초) |
| `kernel_max_priority` | `7` | 커널 로그 발행 우선순위 상한 (예: `4`면 warning 이상) |
| `kernel_include_backlog` | `false` | 시작 시 최근 커널 로그도 방출할지 |

> 그 외 리스트형 파라미터(`vendor_ids`, `keywords` 등)는 `ros2 run`이나 params 파일로 개별
> 노드에 직접 지정하십시오.

> **검증 완료**: FastDDS(localhost)로 `ros2 launch` 실행 시 두 노드(`/usb_camera_monitor`,
> `/kernel_log_monitor`)가 모두 기동하고 인자가 반영됨을 확인했습니다.

---

# `link_latency_monitor` 노드 (지연 vs 끊김)

대상(기본 `8.8.8.8`)에 대한 **종단 latency와 끊김**을 측정합니다. `period_sec`(기본 1초)마다
`timeout_sec`(기본 1초) 데드라인으로 ping 1회를 보냅니다.

- 응답이 timeout 이내 → `~/latency`에 RTT(ms) 발행
- 무응답 → `~/latency`에 `valid=false`, `rtt_ms=NaN`(`.nan`) 발행 (측정 불가를 빈값으로 표현)
- **끊김(outage)** = 첫 실패부터 다음 응답까지. 복구되면 `~/outage`에 그 **지속 시간**을 1회 발행하고
  **끊김 횟수**(`outage_count`)를 +1 (카운터는 launch 시 0부터).

## 발행 토픽

| 토픽 | 타입 | 시점 | 내용 |
|---|---|---|---|
| `~/latency` | `PingLatency` | 매 주기(1Hz) | `valid`, `rtt_ms`(무응답 시 NaN), `outage_count` |
| `~/outage` | `LinkOutage` | 끊김 복구 시 1회 | `duration_sec`(끊김 지속), `outage_count` |

## 판단 기준
- **지연**: `valid=true`인데 `rtt_ms`가 큰 경우
- **끊김**: `valid=false`가 이어지는 구간 → 복구 시 `~/outage`로 지속 시간/횟수 확인
- 끊김 임계(=ping 데드라인)는 `timeout_sec`로 config에서 조정 (기본 1.0초)

## 두 인스턴스 실행 (internet + gateway)

노드는 단일 타깃이라, **인스턴스를 2개** 띄워 목적별로 토픽을 분리합니다(고장 위치 분리에 유용).
`link_latency.launch.py`가 두 인스턴스를 함께 띄웁니다.

| 인스턴스(노드명) | target | 토픽 |
|---|---|---|
| `link_latency_internet` | `8.8.8.8` (종단) | `/link_latency_internet/latency`, `/link_latency_internet/outage` |
| `link_latency_gateway` | `192.168.34.1` (로컬 첫 홉) | `/link_latency_gateway/latency`, `/link_latency_gateway/outage` |

```bash
ros2 launch generate_orbbec_launch link_latency.launch.py
ros2 launch generate_orbbec_launch link_latency.launch.py enable_gateway:=false   # internet만
```

각 메시지의 `target` 필드로도 어느 대상인지 구분됩니다. 두 토픽을 비교하면 "게이트웨이는 정상인데
인터넷만 느림 → 상위(WiFi WAN/인터넷) 문제" 처럼 **원인을 좁힐 수** 있습니다.

## 파라미터 (`config/monitors.yaml`, 인스턴스별 섹션)

`link_latency_internet`, `link_latency_gateway` 두 섹션으로 관리합니다.

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `target` | internet `8.8.8.8` / gateway `192.168.34.1` | ping 대상 |
| `timeout_sec` | `1.0` | ping 데드라인 = 끊김 판정 기준 |
| `period_sec` | `1.0` | 루프/발행 주기 |

> **검증 완료**: 빌드 통과 / outage state machine 단위검증(2회 끊김, 2초·1초 지속) / 두 인스턴스
> 라이브 — `/link_latency_gateway` rtt≈2.9ms, `/link_latency_internet` rtt≈37ms, 무응답 시
> `valid=false rtt_ms=.nan` 확인.

---

# `net_throughput_monitor` 노드 (네트워크 사용량)

네트워크 인터페이스의 **rx/tx 사용량**을 발행합니다. `/sys/class/net/<iface>/statistics`를
읽으므로 **root 불필요**. 인터페이스는 **자동 감지**가 기본입니다.

```bash
ros2 launch generate_orbbec_launch net_throughput_monitor.launch.py
ros2 topic echo /net_throughput_monitor/throughput
```

## 인터페이스 자동 감지

- `interfaces: ['auto']`(기본) → `ip route get <route_target>`로 **현재 egress 인터페이스**를
  매 주기 해석합니다. 머신마다 이름이 달라도(eno1/enp3s0/wlp…) 자동으로 맞고, **유선↔WiFi
  failover도 따라갑니다**(메시지의 `iface`로 현재 사용 인터페이스 확인).
- 특정 인터페이스 고정: `interfaces: ['eno1']` 처럼 명시.

## 발행 토픽

| 토픽 | 타입 | 내용 |
|---|---|---|
| `~/throughput` | `NetThroughput` | `iface`, `rx_bytes`/`tx_bytes`(누적), `rx_bps`/`tx_bps`(B/s rate) |

## 파라미터 (`config/monitors.yaml`)

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `interfaces` | `['auto']` | `'auto'` 또는 명시적 이름 목록 |
| `route_target` | `8.8.8.8` | `'auto'`일 때 egress 해석에 쓰는 목적지 |
| `period_sec` | `1.0` | 샘플/발행 주기 |

> **검증 완료**: 빌드 통과 / 라이브로 egress 자동 감지(`wlp0s20f3`)와 rx_bytes·tx_bytes·
> rx_bps·tx_bps(실시간 변동) 발행 확인 / `all.launch.py`에 포함되어 6개 노드 동시 기동 확인.
> (공유기 인터페이스 `sta1`=WAN/`br-lan`=LAN throughput은 SSH 필요 — 다음 단계)

---

# `router_throughput_monitor` 노드 (공유기 WAN/LAN 사용량)

공유기의 **인터페이스별 rx/tx 사용량**을 SSH로 읽어 발행합니다. 기본 대상은 **WAN(`sta1`)**,
**LAN(`br-lan`)** 이며, 한 번의 SSH로 두 인터페이스를 함께 읽되 **인터페이스마다 별도 토픽**으로
발행합니다(각 토픽이 단일 인터페이스라 `rqt_plot`/PlotJuggler에서 바로 플롯 가능). 토픽 이름에
못 쓰는 `-`는 `_`로 바뀝니다(`br-lan` → `br_lan`).

```bash
ros2 launch generate_orbbec_launch router_throughput_monitor.launch.py
ros2 topic echo /router_throughput_monitor/sta1      # WAN
ros2 topic echo /router_throughput_monitor/br_lan    # LAN
# 플롯 예: /router_throughput_monitor/sta1/rx_bps , /router_throughput_monitor/br_lan/tx_bps
```

## 인증 — 비밀번호 저장 안 함 (SSH 키 필수)
`ssh BatchMode`(키 기반)만 사용합니다. `scripts/setup.sh --wifi-key`로 키를 깔면 됩니다
(wifi_wan_monitor와 같은 키). 키가 없으면 노드는 살아 있되 경고만 남기고 발행하지 않습니다.

## 발행 토픽 / 파라미터

| 토픽 | 타입 | 내용 |
|---|---|---|
| `~/<iface>` (예: `~/sta1`, `~/br_lan`) | `NetThroughput` | `rx_bytes`/`tx_bytes`(누적) + `rx_bps`/`tx_bps`(rate). 인터페이스별 1토픽 |

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `router_host` / `router_user` | `192.168.34.1` / `root` | 공유기 SSH 대상 |
| `interfaces` | `['sta1', 'br-lan']` | WAN, LAN (필요 시 `wifi0`/`wifi1`/`eth0` 등 추가) |
| `period_sec` | `2.0` | SSH 폴링 주기 |

> **검증 완료**: 빌드 통과 / 파서를 실제 라우터 출력으로 검증
> (`sta1` rx 49,145,849·tx 84,377,713 / `br-lan` rx 541,785,232·tx 1,031,511,877) /
> 노드 정상 spin(키 없으면 warn) / `all.launch.py`에 포함되어 7개 노드 동시 기동 확인.

---

# `load_generator` / `load_sink` 노드 (부하 발생 + 수신)

네트워크와 ROS2/Zenoh 미들웨어에 **의도적으로 부하를 발생**시키는 노드입니다.
`load_generator`는 idle 상태로 떠 있다가 **서비스 호출**로 작업을 시작하고, `load_sink`는
상대 머신(또는 같은 호스트의 loopback)에서 트래픽을 받아 수신율을 발행합니다.

> 📖 **각 부하가 어느 계층·구간에 작용하는지**는 다이어그램으로 정리한
> [`docs/load_testing.md`](docs/load_testing.md)를 참조하십시오.

> ⚠️ **트래픽을 실제로 폭주시킵니다.** 본인이 관리 권한을 가진 네트워크에서만, 가급적
> 점검 시간대에 사용하십시오. 운영망 보호를 위해 기본 안전 상한(`max_duration_sec`,
> `max_rate_mbps`)이 걸려 있고, 무제한 블래스트(`rate_mbps: 0`)는 `allow_unlimited: true`를
> 명시해야만 허용됩니다.

## 엔진(`mode`) × 범위(`target`)

| `mode` | 무엇을 부하 주나 | 수신 측 필요 | 적합한 범위 |
|---|---|---|---|
| `ros_pub` | `~/load_topic`에 대용량 페이로드 고속 발행 → **DDS/Zenoh 미들웨어** | `load_sink`(ROS 구독) | ROS2/Zenoh 통신 |
| `tcp` | N개 TCP 소켓으로 버퍼 전송 (리스너 필요) | `load_sink` 또는 `iperf3 -s` | ② 내부 LAN |
| `udp` | UDP 데이터그램 발사 (리스너 없어도 egress 발생) | (불필요) | ① 게이트웨이 링크, ③ WAN 업링크 |
| `iperf3` | `iperf3` 클라이언트 래핑 (정확한 표준 측정) | `iperf3 -s` 또는 공용 서버 | 정밀 측정 |

`target` 키워드 자동 해석: `gateway`(기본 라우트 게이트웨이) / `internal`(`internal_peer` 파라미터)
/ `internet`(`internet_target` 파라미터) / 그 외 문자열은 호스트·IP로 그대로 사용.

## 실행 & 사용법

```bash
# 수신 측(상대 머신, 또는 단일 PC loopback 테스트 시 같은 호스트)
ros2 launch generate_orbbec_launch load_sink.launch.py

# 부하 측
ros2 launch generate_orbbec_launch load_generator.launch.py

# (1) ROS2/Zenoh 미들웨어 부하: 200Hz x 50KB ≈ 80 Mbps
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'ros_pub', publish_hz: 200.0, payload_bytes: 50000, duration_sec: 30.0}"

# (2) 내부 LAN 포화 (load_sink 띄운 피어로 TCP, internal_peer 설정 필요)
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'tcp', target: 'internal', rate_mbps: 500.0, parallel: 8, duration_sec: 30.0}"

# (3) 게이트웨이 링크 / WAN 업링크 포화 (UDP는 리스너 불필요)
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'udp', target: 'gateway', rate_mbps: 800.0, duration_sec: 30.0}"

# 정밀 측정 (대상에 iperf3 -s 필요)
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'iperf3', target: 'internal', rate_mbps: 0.0, allow_unlimited: true, duration_sec: 20.0}"

# 중지 + 실시간 통계
ros2 service call /load_generator/stop std_srvs/srv/Trigger "{}"
ros2 topic echo /load_generator/stats     # tx_bps, msgs_total, errors, detail
ros2 topic echo /load_sink/stats          # rx_bps, bytes_total
```

## `StartLoad` 요청 필드 — 무엇을 어떻게 세팅하나

`ros2 service call ... StartLoad "{ ... }"`의 중괄호 안에 넣는 값들입니다. **`0` 또는 생략하면
노드 파라미터의 기본값**이 적용되므로, 보통은 `mode` + `target` + `rate_mbps`/`duration_sec`
정도만 지정하면 됩니다.

| 필드 | 타입 | 0/생략 시 동작 | 설명 · 설정 팁 |
|---|---|---|---|
| `mode` | string | (필수) | `ros_pub` / `tcp` / `udp` / `iperf3` 중 하나. 잘못되면 거부. |
| `target` | string | (네트워크 모드 필수) | `gateway`/`internal`/`internet` 키워드 또는 호스트·IP 직접. `ros_pub`은 무시(토픽 발행). |
| `port` | uint32 | `default_port`(**5201**) | tcp/udp/iperf3 목적지 포트. `load_sink`/`iperf3 -s`가 듣는 포트와 **일치**해야 함. |
| `rate_mbps` | float64 | 모드별로 다름(아래) | 목표 속도(Mbit/s). 소켓 모드에서 `0`=무제한(→`allow_unlimited` 필요). `max_rate_mbps` 초과 시 자동 클램프. |
| `parallel` | uint32 | `default_parallel`(**4**) | 동시 스트림/소켓 수. 링크를 더 채우려면 8~16. `ros_pub`은 **1로 고정**(대신 `publish_hz`↑). |
| `duration_sec` | float64 | `default_duration_sec`(**30**) | 작업 지속 시간(초). `max_duration_sec`(**300**) 초과 시 클램프. `~/stop`으로 조기 종료 가능. |
| `publish_hz` | float64 | `default_publish_hz`(**100**) | **`ros_pub` 전용** 발행 주파수. 단, `rate_mbps>0`이면 그 값에서 hz를 역산하므로 무시됨. |
| `payload_bytes` | uint32 | `ros_pub`→**65000** / `udp`→**1400** | 메시지/데이터그램 크기(byte). udp는 단편화 피하려면 **≤1472** 권장. tcp는 이 값 대신 `tcp_buffer_bytes` 사용. |
| `allow_unlimited` | bool | `false` | 소켓 모드에서 `rate_mbps: 0`(최대 블래스트)을 쓸 때 **반드시 `true`**. 안전 상한 우회 명시. |

### 모드별로 어떤 필드를 쓰나

| 필드 | `ros_pub` | `tcp` | `udp` | `iperf3` |
|---|:---:|:---:|:---:|:---:|
| `target` | ⛔ 무시 | ✅ 필수 | ✅ 필수 | ✅ 필수 |
| `port` | — | ✅ | ✅ | ✅ |
| `rate_mbps` | 🔸 선택(hz 역산) | 🔸 선택 | 🔸 선택 | 🔸 선택 |
| `parallel` | 🔒 1 고정 | ✅ | ✅ | ✅ (iperf3 `-P`) |
| `duration_sec` | ✅ | ✅ | ✅ | ✅ |
| `publish_hz` | ✅ 핵심 | — | — | — |
| `payload_bytes` | ✅ 핵심 | — (`tcp_buffer_bytes`) | ✅ | — |
| `allow_unlimited` | — | `rate_mbps:0`이면 필수 | `rate_mbps:0`이면 필수 | `rate_mbps:0`이면 필수 |

> **속도 정하는 두 가지 방식** —
> ① 직접: `rate_mbps`로 목표 속도를 못박는다(소켓·iperf3 권장, ros_pub도 가능).
> ② ros_pub 간접: `publish_hz × payload_bytes`로 결정. 예) `200Hz × 50000B = 10MB/s ≈ 80Mbps`.
> `rate_mbps`를 주면 ①이 우선하며 hz는 자동 역산됩니다.

### 먼저 세팅해야 할 노드 파라미터

요청 필드만으로 안 되는 것들은 노드 파라미터(`config/monitors.yaml`)에서 미리 잡아야 합니다.

- **`internal_peer`** — `target: 'internal'`을 쓰려면 **반드시** `load_sink`를 띄운 피어 IP를
  지정해야 합니다(미설정 시 거부). `gateway`/`internet`은 자동 해석되어 설정 불필요.
- **`max_rate_mbps` / `max_duration_sec`** — 안전 상한. 더 센 부하가 필요하면 여기서 올립니다.
- **`ros_reliable`** — `true`면 RELIABLE QoS(재전송 부하 큼), `false`면 BEST_EFFORT.

세팅 방법 두 가지:

```bash
# (A) config/monitors.yaml 의 load_generator 섹션을 수정 후 재빌드
#     load_generator: { ros__parameters: { internal_peer: '192.168.34.50', max_rate_mbps: 2000.0 } }
colcon build --packages-select generate_orbbec_launch && source install/setup.bash

# (B) 런치 없이 즉석에서 -p 로 덮어쓰기 (빠른 테스트용)
ros2 run generate_orbbec_launch load_generator --ros-args \
  -p internal_peer:=192.168.34.50 -p default_port:=5201 -p max_rate_mbps:=2000.0
```

> ⚠️ `port`는 양쪽이 같아야 합니다. `load_sink`의 `tcp_port`/`udp_port`(기본 5201)와
> 요청 `port`(또는 `default_port`)를 맞추십시오. `iperf3`는 대상에서 `iperf3 -s -p <port>`로 서버를 띄워야 합니다.

## 케이스별 종합 정리 (config · 부하 지점 · 서비스 · 필드)

### 한눈에 보는 요약

| 케이스 | 부하가 걸리는 지점 | 사전 config (`load_generator` 섹션) | 수신측 준비 |
|---|---|---|---|
| **A. ROS2 미들웨어(DDS)** | 응용 직렬화 + RMW(Fast DDS) + QoS + 전송 | 기본값 OK (`ros_reliable`로 QoS 선택) | `load_sink`(`enable_ros: true`) |
| **B. ROS2 미들웨어(Zenoh)** | 위와 동일, 단 **Zenoh 전송** | 기본값 + 환경변수 `RMW_IMPLEMENTATION=rmw_zenoh_cpp` | `load_sink`(같은 RMW) + `rmw_zenohd` |
| **C. ② 내부 LAN** | 커널 TCP 스택 + NIC + 스위치 링크 (GW 미경유) | `internal_peer`=피어 IP, `default_port`=싱크 포트 | `load_sink`(`enable_tcp: true`) |
| **D. ① 게이트웨이 링크** | NIC egress + **PC↔공유기 물리 링크** + 공유기 | 불필요 (`gateway` 자동 해석) | 불필요 (UDP fire-and-forget) |
| **E. ③ 외부 WAN** | 공유기 → **ISP 업링크** | `internet_target` (기본 `8.8.8.8`) | 불필요 |
| **F. 정밀 측정(iperf3)** | 커널 소켓 + NIC + 링크 (표준 측정값) | `internal_peer`/대상, `default_port` | 대상에 `iperf3 -s -p <port>` |

---

### A. ROS2 미들웨어 부하 (DDS) — `ros_pub`

**부하 지점**: rclpy → RMW(Fast DDS) → QoS 처리 → 전송(같은 호스트면 공유메모리, 원격이면 NIC).
**config**: 기본값으로 동작. RELIABLE 재전송까지 부하하려면 `ros_reliable: true`(기본), BEST_EFFORT는 `false`.

```bash
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'ros_pub', publish_hz: 200.0, payload_bytes: 50000, duration_sec: 30.0}"
```

| 필드 | 값 | 의미 |
|---|---|---|
| `mode` | `ros_pub` | RMW 경유 토픽 발행으로 미들웨어 부하 (`target` 불필요) |
| `publish_hz` | `200.0` | 초당 200회 발행 |
| `payload_bytes` | `50000` | 메시지당 50 KB → 200×50KB = **10 MB/s ≈ 80 Mbps** |
| `duration_sec` | `30.0` | 30초 후 자동 종료 (생략 시 30, 상한 300) |

---

### B. ROS2 미들웨어 부하 (Zenoh) — `ros_pub` + RMW 전환

**부하 지점**: A와 동일하되 전송이 **Zenoh**(zenohd 라우터 경유). 서비스 호출은 A와 동일.
**config**: 노드 파라미터는 동일. 대신 generator·sink **양쪽**을 같은 RMW로 띄움.

```bash
ros2 run rmw_zenoh_cpp rmw_zenohd &                 # Zenoh 라우터(1회)
export RMW_IMPLEMENTATION=rmw_zenoh_cpp             # load_sink / load_generator 양쪽
ros2 launch generate_orbbec_launch load_sink.launch.py
ros2 launch generate_orbbec_launch load_generator.launch.py
# 서비스 호출 자체는 A 케이스와 100% 동일
```

---

### C. 내부 LAN 포화 (②) — `tcp`

**부하 지점**: 커널 TCP 스택(혼잡제어·ACK) + NIC + 스위치 링크. 같은 서브넷이라 **게이트웨이 미경유**.
**config**: `internal_peer`에 `load_sink` 띄운 피어 IP, `default_port`를 싱크 포트와 일치.

```bash
# config/monitors.yaml -> load_generator: { internal_peer: '192.168.34.50' }   (또는 -p)
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'tcp', target: 'internal', rate_mbps: 500.0, parallel: 8, duration_sec: 30.0}"
```

| 필드 | 값 | 의미 |
|---|---|---|
| `mode` | `tcp` | TCP 스트림 연속 전송 (수신측 `load_sink` 필요) |
| `target` | `internal` | `internal_peer` 파라미터의 IP로 해석 |
| `rate_mbps` | `500.0` | 목표 500 Mbit/s (`max_rate_mbps` 초과 시 클램프) |
| `parallel` | `8` | 동시 TCP 소켓 8개 (링크를 더 채우려면 ↑) |
| `duration_sec` | `30.0` | 30초 |

---

### D. 게이트웨이 링크 포화 (①) — `udp`

**부하 지점**: NIC egress + **PC↔공유기 물리 링크** + 공유기 처리 능력. UDP라 **리스너 없이도** 포화.
**config**: 불필요 — `gateway`는 기본 라우트에서 자동 해석.

```bash
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'udp', target: 'gateway', rate_mbps: 800.0, duration_sec: 30.0}"
```

| 필드 | 값 | 의미 |
|---|---|---|
| `mode` | `udp` | UDP 데이터그램 발사 (fire-and-forget, 수신측 불필요) |
| `target` | `gateway` | 기본 라우트 게이트웨이 IP로 자동 해석 |
| `rate_mbps` | `800.0` | 목표 800 Mbit/s |
| `duration_sec` | `30.0` | 30초 |
| (`payload_bytes`) | 생략 | `udp_payload_bytes` 기본 **1400 B**(단편화 방지) 사용 |

> 측정: `net_throughput_monitor`(호스트 NIC tx)·`link_latency_gateway`(첫 홉 지연)와 함께 보면 효과 확인이 쉽습니다.

---

### E. 외부 WAN 업링크 포화 (③) — `udp`

**부하 지점**: PC → 공유기 → **ISP 업링크**. 인터넷 회선 대역폭을 포화.
**config**: `internet_target` 기본 `8.8.8.8`(필요 시 변경).

```bash
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'udp', target: 'internet', rate_mbps: 0.0, allow_unlimited: true, duration_sec: 20.0}"
```

| 필드 | 값 | 의미 |
|---|---|---|
| `mode` | `udp` | UDP 발사 |
| `target` | `internet` | `internet_target` 파라미터로 해석 |
| `rate_mbps` | `0.0` | **0 = 최대 블래스트** (속도 제한 없음) |
| `allow_unlimited` | `true` | `rate_mbps: 0`을 허용하는 안전 우회 플래그 (없으면 거부) |
| `duration_sec` | `20.0` | 20초 |

> ⚠️ 실제 인터넷 회선을 포화시킵니다. 본인 회선·점검 시간대에만, 약관을 확인하고 사용하십시오.

---

### F. 정밀 측정 — `iperf3`

**부하 지점**: 커널 소켓 + NIC + 링크. iperf3가 **정확한 표준 처리량**을 측정.
**config**: 대상(`internal_peer` 또는 직접 IP), `default_port`. **대상에 iperf3 서버 필수**.

```bash
# 대상 머신:  iperf3 -s -p 5201
ros2 service call /load_generator/start generate_orbbec_launch/srv/StartLoad \
  "{mode: 'iperf3', target: 'internal', parallel: 10, rate_mbps: 0.0, allow_unlimited: true, duration_sec: 20.0}"
```

| 필드 | 값 | 의미 |
|---|---|---|
| `mode` | `iperf3` | iperf3 클라이언트 래핑 (TCP) |
| `target` | `internal` | `internal_peer`로 해석 (iperf3 `-c <host>`) |
| `parallel` | `10` | iperf3 `-P 10` (병렬 스트림) |
| `rate_mbps` | `0.0` | 무제한(최대) 측정 → iperf3 `-b 0` |
| `allow_unlimited` | `true` | `rate_mbps: 0` 허용 (필수) |
| `duration_sec` | `20.0` | iperf3 `-t 20`. 결과는 `~/stats`의 `detail`에 Mbps로 요약 |

---

## Zenoh로 테스트 (DDS와 동일 노드)

`ros_pub`은 **RMW에 독립적**이므로, 같은 노드를 RMW만 바꿔 띄우면 그대로 Zenoh 부하 테스트가
됩니다. (rmw_zenoh 설치 전제)

```bash
# 별도 터미널에서 Zenoh 라우터 1회 기동
ros2 run rmw_zenoh_cpp rmw_zenohd

# generator / sink 양쪽 모두 같은 RMW로
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
ros2 launch generate_orbbec_launch load_sink.launch.py
ros2 launch generate_orbbec_launch load_generator.launch.py
# 이후 ros_pub 작업을 호출하면 /load_sink/stats 의 rx_bps 로 Zenoh 처리율 확인
```

## 서비스 / 토픽 / 파라미터

| 인터페이스 | 타입 | 내용 |
|---|---|---|
| `/load_generator/start` | `StartLoad` (srv) | 작업 시작 (한 번에 1개; 실행 중이면 거부) |
| `/load_generator/stop` | `std_srvs/Trigger` | 실행 중 작업 중지 |
| `/load_generator/stats` | `LoadStats` | `tx_bps`, `bytes_total`, `msgs_total`, `errors`, `detail` |
| `/load_generator/load_topic` | `std_msgs/UInt8MultiArray` | `ros_pub` 페이로드 스트림 |
| `/load_sink/stats` | `LoadStats` | `rx_bps`, `bytes_total`(수신 누적) |

| 주요 파라미터(`load_generator`) | 기본값 | 설명 |
|---|---|---|
| `internal_peer` | `''` | 범위 `internal` 대상 (load_sink 띄운 피어 IP) — **설정 필요** |
| `internet_target` | `8.8.8.8` | 범위 `internet` 대상 (WAN 업링크) |
| `default_port` | `5201` | tcp/udp/iperf3 포트 (iperf3 기본) |
| `default_parallel` | `4` | 스트림/소켓 수 (요청 `parallel`=0일 때) |
| `max_duration_sec` | `300.0` | **안전**: 작업 최대 지속 시간 (0=무제한) |
| `max_rate_mbps` | `1000.0` | **안전**: 최대 rate 상한 (0=무제한) |
| `ros_reliable` | `true` | RELIABLE QoS 부하 / `false`=BEST_EFFORT |

> **검증 완료**: colcon 빌드 통과(`StartLoad.srv`/`LoadStats.msg` 생성, 두 노드 설치) /
> loopback 스모크 테스트 — `ros_pub` 200Hz×50KB에서 `tx_bps`≈10 MB/s 측정, `udp` 100 Mbps
> 목표 대비 `tx_bps`≈12.5 MB/s 측정 / 안전 cap 동작 확인(rate 5000→1000, duration 9999→300) /
> 무제한 블래스트(`rate_mbps: 0`)는 `allow_unlimited` 없으면 거부 / 한 번에 1개 작업 가드 동작.
