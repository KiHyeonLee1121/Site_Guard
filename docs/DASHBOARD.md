# 관리자 대시보드

~~~bash
./scripts/run_mock.sh --config config/demo.yaml --realtime --stay-open
~~~

[로컬 대시보드](http://127.0.0.1:8765)에서 입력 유형, 프레임 크기, 객체 검출 박스, ID·클래스·신뢰도, ROI, 체류, LED·스피커 명령, PIR, 전송 상태와 최근 이벤트를 볼 수 있습니다. Mock은 가상 프레임과 검출 박스로 표시됩니다. 실제 영상은 카메라 또는 저장 영상 실행 명령에서 선택합니다.

ROI 편집에서 단계를 고르고 영상을 클릭해 꼭짓점을 추가합니다. 꼭짓점을 드래그해 위치를 바꾸고 이름을 지정합니다. 선택한 구역은 삭제 후 저장하거나 다시 불러올 수 있습니다. 저장 전에 다각형의 좌표 범위, 꼭짓점, 경계 교차 여부를 검증합니다. 동시 저장 충돌 시 최신 설정을 다시 불러옵니다. 설정 파일은 원자적으로 교체됩니다.

HTTP 프레임은 기본 최대 5Hz와 너비 640px JPEG 프리뷰를 사용합니다. Canvas는 원본 해상도에 맞춰 박스 및 ROI를 그립니다. `GET /api/status`, `GET /api/frame.jpg`, `GET /api/events`, `GET /api/events/<이벤트 ID>`, `GET /api/roi`, `GET /api/policy`가 조회를 제공합니다. 변경은 JSON `PUT /api/roi`와 현재 revision, `X-SiteGuard-ROI: 1`가 필요합니다.

## Wi-Fi 시연

Jetson과 노트북을 같은 실습용 AP에 연결합니다. Jetson Nano에 인터페이스가 없으면 Linux 드라이버가 맞는 USB Wi-Fi 어댑터를 사용합니다. Jetson이 받은 주소를 `ip -brief address`로 확인합니다. Ethernet으로도 개발할 수 있습니다.

기본 loopback을 유지하고 노트북에서 SSH 터널로 확인할 수 있습니다.

~~~bash
ssh -N -L 8765:127.0.0.1:8765 jetson@JETSON_IP
~~~

실습망에서 Jetson 사설 주소로 직접 접속할 경우 `.env`에 `SITEGUARD_DASHBOARD_TOKEN`을 설정합니다. 24자 이상 토큰과 사용자명 `siteguard`로 HTTP Basic 인증을 합니다. `--dashboard-host JETSON_IP`로 바인딩하면 지정된 인터페이스의 주소로 접속할 수 있습니다. 영상 및 인증을 암호화하는 접속이 필요하면 SSH 터널을 사용합니다.
