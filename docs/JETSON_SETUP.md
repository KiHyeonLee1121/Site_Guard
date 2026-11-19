# Jetson Nano 준비와 검증

~~~bash
git clone https://github.com/KiHyeonLee1121/Site_Guard.git
cd Site_Guard
./scripts/check_jetson_env.sh
./scripts/bootstrap_jetson.sh --check
./scripts/bootstrap_jetson.sh --install
./scripts/install_jetson_inference.sh
./scripts/setup_model.sh jetson
SITEGUARD_PYTHON=.venv-jetson/bin/python ./scripts/run_mock.sh --benchmark
~~~

`--check`는 운영체제·Python 조건과 Mock을 검사합니다. `--install`은 현재 JetPack 패키지 저장소에서 OpenCV·NumPy·venv를 설치합니다. NVIDIA CUDA와 TensorRT 개발 패키지가 이미 있는지 확인하고, 빠져 있으면 보드의 JetPack 버전에 맞는 NVIDIA 패키지를 준비한 후 설치를 다시 실행합니다. NVIDIA 이미지의 `/etc/nv_tegra_release`, CUDA, TensorRT, RAM, 저장 공간, 포트 이름과 권한을 기록합니다.

기본 SSD 바인딩이 없다면 소스 빌드를 시도합니다. 스크립트는 jetson-inference 커밋을 고정하고 자동 의존성·Torch 설치를 끈 상태에서 빌드합니다. 설치 공간과 최초 엔진 컴파일 시간을 확보합니다. 장비에서 검증하기 전에 microSD의 현재 설정과 프로젝트 데이터를 백업해두면 복구가 쉽습니다. [jetson-inference 소스 빌드 안내](https://github.com/dusty-nv/jetson-inference/blob/45da40a8f3c180191b269f57f736caaa025b8a69/docs/building-repo-2.md)

~~~bash
ls -l /dev/video* /dev/serial/by-id/
./scripts/run_camera.sh --camera-index 0 --dry-run
~~~

프리뷰와 ROI를 조정하고 Arduino 펌웨어와 출력 회로를 확인한 다음 장치를 연결합니다. 고정 경로가 있으면 tty 번호 대신 `/dev/serial/by-id/…`를 지정합니다.

~~~bash
./scripts/run_camera.sh --camera-index 0 --serial-port /dev/ttyACM0 --record
~~~

USB 카메라에 대체 캡처 경로가 필요하면 OpenCV GStreamer 빌드 확인 후 `--gstreamer 'v4l2src device=/dev/video0 ! videoconvert ! appsink drop=true max-buffers=1 sync=false'`를 사용할 수 있습니다. 실기기에서 정확한 해상도와 FPS, 카메라 권한을 확인합니다.

## YOLO11n TensorRT FP16 실험

PC의 [YOLO 환경](../README.md)에서 ONNX와 JSON을 만듭니다.

~~~bash
./scripts/setup_model.sh yolo
.venv-pc/bin/python tools/export_yolo_onnx.py --size 320
~~~

생성된 `yolo11n-320.onnx`와 `yolo11n-320.json`을 Jetson의 `models/local/`에 복사합니다. JetPack과 호환되는 PyCUDA Python 바인딩을 준비하고 `check_jetson_env.sh`에 `pycuda.driver`와 `tensorrt`가 표시되는지 확인합니다. 배포판에서 `python3-pycuda`를 제공하면 해당 패키지를 우선 검토합니다.

~~~bash
./scripts/build_tensorrt.sh models/local/yolo11n-320.onnx
./scripts/run_camera.sh --detector tensorrt --device cuda:0 --input-size 320 \
  --model models/local/yolo11n-320.engine --metadata models/local/yolo11n-320.json --dry-run
~~~

엔진은 대상 Nano에서 생성합니다. TensorRT parser나 장치에서 빌드가 실패하면 저장된 빌드 오류를 확인하고 SSD 프로필로 진행합니다. 416·640도 각각 별도 export와 빌드를 거칩니다.

## 자동 시작과 측정

`deployment/jetson/siteguard.service`를 사용하려면 `/opt/siteguard`에 저장소와 가상환경을 두고 설치 계정 `siteguard`가 저장소의 설정·데이터 경로를 읽고 쓸 수 있도록 구성합니다. 사용 중인 경로와 계정 요건에 맞춰 서비스 파일을 조정합니다.

~~~bash
sudo install -m 0644 deployment/jetson/siteguard.service /etc/systemd/system/siteguard.service
sudo systemctl daemon-reload
sudo systemctl enable --now siteguard
journalctl -u siteguard -f
~~~

~~~bash
SITEGUARD_PYTHON=.venv-jetson/bin/python ./scripts/benchmark.sh \
  --config config/jetson.yaml --source camera --max-frames 300
tegrastats --interval 1000
~~~

같은 테스트 영상과 시간 구간에서 입력별 처리 FPS, 캡처 드롭, 추론 지연, p95, RAM 및 전력 지표를 기록합니다. `capture_to_decision_ms`는 프레임 수신부터 정책 결정까지의 시간입니다. Serial 연동 실행의 `serial_ack_ms`에는 재시도 시간이 포함됩니다. 실제 빛·음향까지의 지연은 외부 측정으로 확인합니다. 전력 측정 시 CSE4316 Week 09 Lecture 02의 에너지·전력과 지연 지표를 참고합니다. 소비전력 개선 수치는 측정 후 기록합니다.
