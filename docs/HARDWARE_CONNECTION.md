# 하드웨어 연결과 확인

실제 장치의 모델명, 공급 전압, 신호 전압, 허용 전류와 USB 포트를 먼저 기록합니다. Nano 33 BLE Sense 계열 GPIO는 3.3V입니다. 아래 표는 펌웨어의 제어 신호 핀입니다. [Arduino 공식 보드 문서](https://docs.arduino.cc/tutorials/nano-33-ble-sense/cheat-sheet)

| Arduino 핀 | 설정 | 대상 |
| --- | --- | --- |
| USB | CDC Serial | Jetson USB 호스트 |
| D2 | 디지털 입력, 기본 비활성 | 3.3V 허용 PIR, `ENABLE_PIR=1`로 활성화 |
| D5 | PWM 로직 출력 | LED 구동 회로 PWM 입력 또는 적절한 MOSFET 게이트 드라이버 |
| D6 / D7 | 100ms 트리거 | 사람 일반 / 높은 단계 음성 |
| D8 / D9 | 100ms 트리거 | 개 일반 / 높은 단계 비음성 |
| D10 | 100ms STOP 트리거 | 외부 음향 모듈 재생 중단 |

LED는 전류 정격에 맞는 외부 구동 회로와 전원으로 연결합니다. 스피커는 음향 재생 모듈 또는 앰프 출력에 연결합니다. 다른 로직 전압 장비에는 적절한 레벨 시프터나 절연 입력을 사용합니다. 외부 음향 장치가 STOP 또는 독립 트리거 입력을 지원하는지 확인합니다. 다른 규격의 직렬식 음향 모듈은 `setSound` 주변 드라이버를 교체합니다.

Arduino IDE에서는 실제 보드에 맞는 Arduino Mbed OS Nano Boards와 보드 항목을 선택합니다. Nano 33 BLE 계열의 CLI 예시는 아래와 같습니다.

~~~bash
arduino-cli core install arduino:mbed_nano@4.3.1
arduino-cli compile --fqbn arduino:mbed_nano:nano33ble firmware/siteguard_arduino
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:mbed_nano:nano33ble firmware/siteguard_arduino
~~~

1. Jetson에서 `ls -l /dev/serial/by-id/`와 `ls -l /dev/video*`로 실제 포트를 확인합니다.
2. 포트 권한과 사용자 `dialout`, `video` 그룹을 확인합니다.
3. 실제 부하를 연결하기 전에 ACK, D5 PWM, D6–D10 펄스와 통신 단절 후 OFF를 측정합니다.
4. 장치를 연결하고 낮은 밝기에서 소리, STOP, LED, PIR을 확인합니다.
5. IR 영상은 카메라가 지원하는 모드에서 테스트합니다.
