# 검증 보고서

## 개발 환경 결과

| 항목 | 명령 또는 조건 | 결과 |
| --- | --- | --- |
| Python 3.12, OpenCV·NumPy | `python3 -m unittest discover -s tests -v` | 35개 통과, 실패 0 |
| Python 3.6.15, x86_64 | 동일 명령 | 핵심 32개 통과, OpenCV 전용 3개 건너뜀 |
| Mock 통합 | `./scripts/run_mock.sh --benchmark` | 720 프레임, 1차 경고 2건, 높은 경고 1건, 해제 및 SQLite 장치 응답 기록 확인 |
| Arduino 호스트 핀 모의 검사 | `./scripts/test_firmware_host.sh` | SG1 프레이밍, ACK/NACK, PIR, 명령 재시도 중복 제거, STOP과 타임아웃 확인 |
| Arduino 보드용 컴파일 | `arduino-cli compile --fqbn arduino:mbed_nano:nano33ble firmware/siteguard_arduino` | Arduino Mbed Nano 코어 4.3.1 컴파일 성공 |
| 실제 개 영상 | YOLO11n 320, CPU, 90프레임, Mock 출력, `--record` | 사람·개 검출 406건, 중요 이벤트 4건, 1차 경고 2건, 재생 가능한 이벤트 클립 2개 생성 |
| ONNX 추론 및 후처리 | opset 12, CPU ONNX Runtime, 동일 영상 90프레임 | 사람 396건·개 8건 처리, 입력 1×3×320×320 및 출력 1×84×2100 확인 |
| HTTP 오프라인 재동기화 | 로컬 Mock 수신기 종료 후 복구, 같은 ID 재전송 | pending → sent 전환, 수신기 이벤트 1회 저장 |
| 대시보드 API | 정적 파일, 상태, ROI 쓰기 권한, 원본 출처 확인 | Python 테스트 통과 |
| 모델·패키지 | 두 모델 번들 SHA-256, Python wheel 설치 후 Mock | 다운로드 무결성 및 패키지에 포함된 기본 설정 확인 |

Python 3.6 테스트는 새 glibc 환경에 빌드한 별도 인터프리터에서 진행했습니다. 현지 libffi와의 충돌로 테스트 빌드의 ctypes 확장을 제외했습니다. SiteGuard 표준 라이브러리 경로와 테스트 코드는 동일합니다. 장치 배포는 JetPack에 들어 있는 시스템 Python을 사용합니다.

실제 영상의 출처는 Nesnad의 CC BY-SA 4.0 영상입니다. 로컬 시험용으로 640px, 10 FPS로 변환하고 음성을 제거했습니다. 영상과 녹화 결과는 저장소에 포함하지 않습니다. 영상은 검출과 연동 테스트용으로 사용했으며 현장 성능이나 오검출률의 측정 데이터에는 포함하지 않습니다. [영상 원본](https://commons.wikimedia.org/wiki/File:Pro_dog_walker_-_Tokyo_-_2024_Nov_1.webm) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

## 실기기 검증

| 항목 | 확인할 점 |
| --- | --- |
| Jetson Nano 4GB | L4T·CUDA·TensorRT·Python, SSD 로드, UFF 엔진 캐시, YOLO 엔진 빌드, FPS·p95·RAM |
| USB 카메라 / IR | 카메라 모드별 해상도와 지연, 복구 동작, 저조도 오검출 및 실제 ROI |
| Arduino / PIR / 출력 회로 | 업로드, 실물 USB ACK, 센서 입력, 광량·스피커 구동과 종료 시 출력 |
| Wi-Fi / WISE-PaaS | 실습 AP, 노트북 브라우저 연결 및 이벤트 전송, 실제 테넌트 인증·스키마 |
| 장시간 감시 | 메모리·전력·디스크 사용 추이, 입력 장애 후 복구, 감시 중 중첩 경고 |

최신 GitHub 실행 상태는 [Actions](https://github.com/KiHyeonLee1121/Site_Guard/actions)에서 확인할 수 있습니다.
