# Jetson Nano 4GB 호환성

JetPack 4.6.6은 Jetson Nano를 지원하는 L4T R32 계열의 최종 릴리스입니다. JetPack 4.6.1 계열 구성은 Ubuntu 18.04 기반, CUDA 10.2, TensorRT 8.2.1을 사용합니다. 이미지와 설치 패키지에 따라 실제 버전은 다를 수 있으므로 먼저 장치에서 확인합니다. [JetPack 4.6.6](https://developer.nvidia.com/jetpack-sdk-466) · [L4T R32.7.6](https://developer.nvidia.com/embedded/linux-tegra-r3276)

| 후보 | 선택 | 확인 지점 |
| --- | --- | --- |
| SSD-MobileNet-v2 / jetson-inference | Jetson 기본 | 자체 Python 3.6 바인딩, COCO 라벨, UFF/TensorRT 사용. Jetson에서 네이티브 빌드 및 FPS 확인 |
| YOLO11n / Ultralytics | PC와 개 영상 시연 기본 | Python 3.12와 CPU에서 검증. JetPack 시스템 Python과 분리 |
| YOLO11n / TensorRT FP16 | Jetson 후보 | PC에서 opset 12 ONNX를 만들고, Nano에서 TensorRT 8 ONNX parser 및 엔진 빌드 확인 |
| YOLOv5n 계열 | 후속 비교 후보 | 출력을 따로 변환해야 함. 이번 기본 백엔드는 SSD와 YOLO11 |

Ultralytics에는 JetPack 4 대상 Dockerfile이 있고 Python 3.8과 해당 ARM 빌드의 Torch를 준비합니다. 태그와 구성은 바뀔 수 있으므로 최신 태그를 기본 배포에 사용하지 않습니다. 컨테이너로 검증할 경우 장비의 L4T R32 태그, 실제 이미지 digest, 카메라·USB 접근, 4GB의 메모리 사용량을 기록합니다. [Ultralytics JetPack 4 Dockerfile](https://github.com/ultralytics/ultralytics/blob/main/docker/Dockerfile-jetson-jetpack4)

SiteGuard의 판단·Mock은 Python 3.6 표준 라이브러리로 실행합니다. 설치 스크립트는 L4T R32의 기본 Python을 유지하고 시스템 패키지를 볼 수 있는 가상환경을 생성합니다. OpenCV, CUDA, TensorRT는 호스트 BSP와 패키지 조합을 사용합니다.
