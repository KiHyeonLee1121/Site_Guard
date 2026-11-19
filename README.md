# SiteGuard

SiteGuard는 공사 현장 자재 구역의 사람과 개를 감지하고, 접근 구역과 체류 시간을 바탕으로 LED와 음향을 제어하는 오프라인 우선 Edge AI 엔진입니다. 카메라, 영상 파일, Mock 입력은 같은 추적·ROI·상태머신을 사용합니다. 현장 이벤트는 SQLite에 저장됩니다.

## PC에서 바로 실행

~~~bash
git clone https://github.com/KiHyeonLee1121/Site_Guard.git
cd Site_Guard
./scripts/run_mock.sh --benchmark
python3 -m unittest discover -s tests -v
./scripts/test_firmware_host.sh
~~~

Mock은 Python 표준 라이브러리만 사용합니다. 기본 시나리오는 ROI 1 통과, 사람과 개의 ROI 2 체류, ROI 3 직접 진입, 경고 해제를 실행합니다. 화면에서 보려면 다음 명령을 실행하고 [대시보드](http://127.0.0.1:8765)를 엽니다.

~~~bash
./scripts/run_mock.sh --config config/demo.yaml --realtime --stay-open
~~~

## PC에서 실제 개 영상 검출

Linux x86-64와 Python 3.10–3.12에서 CPU 추론을 실행합니다.

~~~bash
python3 -m venv .venv-pc
.venv-pc/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 torchvision==0.21.0
.venv-pc/bin/python -m pip install -r deployment/development/requirements-yolo.txt
./scripts/setup_model.sh yolo
SITEGUARD_PYTHON=.venv-pc/bin/python ./scripts/run_video.sh /path/to/dog.mp4 \
  --detector yolo --dry-run --dashboard --realtime --stay-open
~~~

대시보드의 ROI 편집기에서 기본 예시를 실제 영상과 카메라 설치 위치에 맞춰 보정합니다.

## Jetson Nano 4GB에서 실행

최초 설치와 모델 준비에 네트워크가 필요합니다. 준비된 장비에서 판단·경고·SQLite 기록은 인터넷 없이 동작합니다.

~~~bash
./scripts/check_jetson_env.sh
./scripts/bootstrap_jetson.sh --install
./scripts/install_jetson_inference.sh
./scripts/setup_model.sh jetson
SITEGUARD_PYTHON=.venv-jetson/bin/python ./scripts/run_mock.sh --benchmark
./scripts/run_camera.sh --camera-index 0 --dry-run
~~~

카메라와 ROI 확인, 펌웨어 업로드를 마친 뒤 Serial을 연결합니다.

~~~bash
./scripts/run_camera.sh --camera-index 0 --serial-port /dev/ttyACM0 --record
~~~

기본 Jetson 백엔드는 COCO SSD-MobileNet-v2와 JetPack 시스템 TensorRT를 사용합니다. YOLO11n ONNX의 Jetson TensorRT FP16 빌드는 대상 장비에서 검증합니다. 설치, 측정, 확인 항목은 [Jetson 설치](docs/JETSON_SETUP.md), [호환성](docs/JETSON_COMPATIBILITY.md), [검증 보고서](docs/TEST_REPORT.md)에 있습니다.

## 작업 문서

| 작업 | 문서 |
| --- | --- |
| 전체 시스템과 팀 인터페이스 | [아키텍처](docs/ARCHITECTURE.md) · [모듈 계약](docs/MODULE_INTERFACES.md) · [팀 개발](docs/TEAM_DEVELOPMENT.md) |
| 카메라 보정과 장치 연결 | [ROI 정책](docs/ROI_POLICY.md) · [하드웨어](docs/HARDWARE_CONNECTION.md) · [Serial](docs/SERIAL_PROTOCOL.md) |
| 관리자 화면과 Wi-Fi | [대시보드](docs/DASHBOARD.md) |
| 강의실 시연 | [시연 가이드](docs/DEMO_GUIDE.md) |
| 모델 출처 및 다운로드 | [모델 관리](models/README.md) |
| 오프라인 큐와 WISE-PaaS | [클라우드 연결](docs/CLOUD.md) |

기본 설정은 `config/default.yaml`에 있으며 JSON 호환 YAML입니다. 모든 실행 옵션은 `python3 -m siteguard --help`로 확인합니다. 소스코드 라이선스는 [MIT](LICENSE)이며 외부 모델과 라이브러리에는 각 제공자의 조건이 적용됩니다.
