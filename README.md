# generate-orbbec-launch

연결된 Orbbec(VID `2bc5`) 카메라들을 자동으로 탐지하고, 대화형으로 이름·primary 카메라를 지정해
ROS 2 멀티 카메라 동기화 런치 파일(`multi_camera_synced.launch.py`)을 생성하는 스크립트입니다.

## 동작 방식

1. **자동 탐지** — `/sys/bus/usb/devices`를 훑어 VID `2bc5`인 장치를 모두 찾고, 각 장치의
   시리얼 번호와 USB 포트(busid)를 수집합니다. (중복 sysfs 노드는 시리얼 기준으로 제거)
2. **대화형 이름 지정** — 탐지된 카메라마다 시리얼·USB 포트를 보여주고 이름을 입력받습니다.
   빈 이름·중복 이름은 거부합니다.
3. **primary 선택** — 어느 카메라를 primary로 쓸지 인덱스로 고릅니다. primary는
   `software_triggering`, 나머지는 모두 `hardware_triggering`으로 설정됩니다.
4. **런치 파일 생성** — 카메라 대수(`device_num`)와 트리거 모드를 반영해
   `multi_camera_synced.launch.py`를 만듭니다. 동기화 안정성을 위해 secondary 카메라들이
   먼저 올라온 뒤, primary 카메라는 `TimerAction(period=3.0)`으로 3초 지연 후 마지막에 실행됩니다.

## 사용법

```bash
./generate_orbbec_launch.sh            # 실제 하드웨어 탐지 후 생성
./generate_orbbec_launch.sh --dry-run  # 가짜 장치 목록으로 흐름만 확인 (하드웨어 불필요)
./generate_orbbec_launch.sh --help     # 사용법 출력
```

### `--dry-run`

하드웨어가 연결되어 있지 않아도 전체 흐름(탐지 → 이름 지정 → primary 선택 → 파일 생성)을
점검할 수 있도록 고정된 가짜 장치 4대를 사용합니다. sysfs에 접근하지 않습니다. 생성된
런치 파일은 실제 하드웨어로 다시 검증한 뒤 사용하십시오.

## 요구 사항

- Bash
- Linux (USB 장치 탐지에 `/sys/bus/usb/devices` 사용)
- ROS 2 + `orbbec_camera` 패키지 (생성된 런치 파일 실행 시)

## 생성 결과 예시

`gemini_330_series.launch.py`를 카메라마다 include 하며, 각 카메라에 다음 인자를 주입합니다.

- `camera_name` — 사용자가 지정한 이름
- `usb_port` — 자동 탐지된 USB 포트
- `device_num` — 탐지된 카메라 총 대수
- `sync_mode` — primary는 `software_triggering`, 그 외는 `hardware_triggering`
- `config_file_path` — `orbbec_camera` 패키지의 `config/camera_params.yaml`
