# generate_orbbec_launch

여러 대의 Orbbec Gemini 카메라를 실행하기 위한 **ROS 2 패키지**(`ament_cmake`, C++/Python
혼합 가능, 대상 배포판 **Jazzy**)입니다. 핵심 도구로, 연결된 Orbbec(VID `2bc5`) 카메라를
자동 탐지하고 대화형으로 이름·primary를 지정해 멀티 카메라 런치 파일을 생성하는 스크립트를
포함합니다.

## 패키지 구조

```
generate_orbbec_launch/
├── package.xml                 # ament_cmake 패키지 매니페스트
├── CMakeLists.txt              # 빌드/설치 규칙 (C++·Python 노드 추가 지점 주석으로 표시)
├── launch/                     # 생성된 런치 파일이 저장되는 위치 (colcon이 설치)
├── scripts/
│   └── generate_orbbec_launch.sh   # 런치 파일 생성 스크립트 (ROS 노드가 아닌 순수 스크립트)
└── generate_orbbec_launch/     # 향후 Python 노드를 담을 모듈
    └── __init__.py
```

> 노드는 아직 추가되지 않았습니다. `CMakeLists.txt`와 `package.xml`에 C++(`rclcpp`)·
> Python(`rclpy`) 노드를 추가할 지점이 주석으로 표시되어 있습니다.

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

## 생성 결과 예시

`gemini_330_series.launch.py`를 카메라마다 include 하며, 각 카메라에 다음 인자를 주입합니다.

- `camera_name` — 사용자가 지정한 이름
- `usb_port` — 자동 탐지된 USB 포트
- `device_num` — 탐지된 카메라 총 대수
- `sync_mode` — 동기화 모드에서는 primary가 `software_triggering`, 그 외는
  `hardware_triggering`. 비동기(`--no-sync`) 모드에서는 모든 카메라가 `standalone`
  (또는 `free_run`)
- `config_file_path` — `orbbec_camera` 패키지의 `config/camera_params.yaml`
