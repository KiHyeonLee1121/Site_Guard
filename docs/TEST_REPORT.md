# 검증 보고서

## 강의실 시연 사전 검증

YOLO11n CPU, 검출 신뢰도 0.45, 기본 경고 정책, Mock 장치 출력으로 검사했습니다. 강의실 영상은 사람 한 명을 합성한 예행 영상이며, 원본 테이프의 모서리를 기준으로 세 다각형을 설정했습니다.

| 입력 | 결과 |
| --- | --- |
| 예행 영상 203프레임, YOLO 입력 크기 320 | 한 사람에게 두 ID 및 `critical` 2건. 이탈 시 `cleared` 없이 추적 만료로 해제 |
| 동일 영상 203프레임, YOLO 입력 크기 640 | 같은 ID에서 `critical` 1건(4.33초), `cleared` 1건(11.73초). ROI 2는 5초 미만 통과. 결과 MP4에 1280×720, 15 FPS, 203프레임 유지 |
| 예행 영상의 ROI 2 구간에서 한 프레임을 6초 더 유지한 293프레임 입력, YOLO 640 | ID 1에서 5초 체류 후 `warning`(7.93초), `critical`(10.40초), `cleared`(17.73초) 각 1건 |
| 실제 보행자 영상 120프레임, 수동으로 그린 가상 ROI, YOLO 640 | 여러 사람 검출, ROI 2 체류·ROI 3 진입·이탈 이벤트 및 결과 MP4 생성 확인. 다중 객체 ID 정확도는 별도 평가가 필요 |
| Python 3.12, OpenCV·NumPy | 자동 테스트 36개 통과. 좌우로 인접한 테이프 ROI의 순차 경고·해제, 결과 MP4 프레임·자막, 보정 파일 누락과 파일 덮어쓰기 차단 포함 |

실제 보행자 영상은 [OpenCV vtest 샘플](https://github.com/opencv/opencv/blob/4.x/samples/data/vtest.avi)입니다. 640은 YOLO 영상 검증 설정에 적용했습니다. 팀 강의실 실촬영, 가림막 통과, Jetson 카메라의 처리 속도 및 SSD 검출률, 실제 Arduino LED·음성, IR·WISE-PaaS는 현장에서 확인합니다.

## 초기 개발 환경 결과

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
