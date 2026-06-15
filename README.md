# generate_orbbec_launch

여러 대의 Orbbec Gemini 카메라를 실행하기 위한 **ROS 2 패키지**(`ament_cmake`, C++/Python
혼합 가능, 대상 배포판 **Jazzy**)입니다. 두 가지 핵심 기능을 제공합니다.

1. 연결된 Orbbec(VID `2bc5`) 카메라를 자동 탐지하고 대화형으로 이름·primary를 지정해 멀티
   카메라 런치 파일을 생성하는 **스크립트**(`scripts/generate_orbbec_launch.sh`).
2. USB 버스에 연결된 카메라 목록·포트·USB 세대를 토픽으로 발행하는 **모니터 노드**
   (`usb_camera_monitor`).
3. 카메라/USB 관련 커널 로그(dmesg)를 토픽으로 발행하는 **모니터 노드**
   (`kernel_log_monitor`).
4. 공유기 WiFi WAN(업링크) 신호 dBm을 토픽으로 발행하는 **모니터 노드**
   (`wifi_wan_monitor`) — 유선 연결 머신용.

## 패키지 구조

```
generate_orbbec_launch/
├── package.xml                 # ament_cmake 패키지 매니페스트 (rosidl 메시지 생성 포함)
├── CMakeLists.txt              # 빌드/설치 규칙 (C++ 노드 추가 지점 주석으로 표시)
├── msg/
│   ├── OrbbecUsbDevice.msg      # USB 카메라 1대의 정보
│   ├── OrbbecUsbDeviceArray.msg # 탐지된 카메라 스냅샷
│   ├── KernelLogEntry.msg       # 커널 로그 1줄
│   └── WifiWanStatus.msg        # 공유기 WiFi WAN 신호
├── launch/
│   └── monitors.launch.py       # 두 모니터 노드를 함께 실행 (생성 런치 파일과 달리 git 추적)
├── nodes/
│   ├── usb_camera_monitor.py    # USB 카메라 인벤토리 모니터 노드 (rclpy)
│   ├── kernel_log_monitor.py    # 커널 로그(dmesg) 모니터 노드 (rclpy)
│   └── wifi_wan_monitor.py      # 공유기 WiFi WAN 신호 모니터 노드 (rclpy)
└── scripts/
    └── generate_orbbec_launch.sh   # 런치 파일 생성 스크립트 (ROS 노드가 아닌 순수 스크립트)
```

## 빌드

```bash
cd ~/ros2_ws        # colcon 워크스페이스의 src/ 아래에 이 패키지를 둡니다
colcon build --packages-select generate_orbbec_launch
source install/setup.bash
```

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
| `~/wifi_wan` | `generate_orbbec_launch/WifiWanStatus` (reachable, essid, signal_dbm, noise_dbm, quality, bitrate) |
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
