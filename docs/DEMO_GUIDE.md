# 강의실 시연

시작 전에 입력별 실행 명령, USB 포트, ROI 화면, Arduino 펌웨어, 출력 장치, 저장 경로를 확인합니다. 녹화 계획은 약 2시간 기준으로 입력과 조명 바꾸는 시간을 포함해 아래 순서로 진행할 수 있습니다.

| 장면 | 준비와 실행 | 성공 조건 |
| --- | --- | --- |
| 1. 사람 ROI 1 통과 | `./scripts/run_camera.sh --dry-run`으로 ROI를 확인한 뒤 실제 장치 모드에서 통로를 걷습니다 | 사람 ID와 ROI 1 표시, LED·음향 OFF |
| 2. 사람 ROI 2 체류 | ROI 2에 서서 기본 5초 이상 기다립니다 | 체류값 증가, 1차 경고, LED와 음성, 이벤트 기록 |
| 3. ROI 3 직접 확인 | 객체가 ROI 3에서 먼저 보이게 하고 기본 연속 2회 검출을 확인합니다 | ROI 2 대기 없이 높은 단계와 critical 기록 |
| 4. 경고 해제 | 2·3단계 밖으로 나와 1초 이상 머뭅니다 | CLEARING 뒤 출력 OFF와 cleared 기록 |
| 5. 실제 개 영상 | PC에서 README의 `run_video.sh`를 쓰고, 장치가 붙으면 `--serial-port /dev/ttyACM0`로 실행합니다 | dog 검출과 발 기준점, ROI·경고 정책, 비음성 명령 |
| 6. 오프라인과 재전송 | [클라우드 시연](CLOUD.md)의 수신기를 끄고 이벤트를 만들고 다시 연결합니다 | 로컬 기록과 경고 유지, 복구 후 sent |
| 7. 야간 IR | 실제 카메라를 IR 지원 상태로 설치한 뒤 `./scripts/run_camera.sh --record` | 저조도 검출과 LED 전환, 조명 전후 영상 확인 |
| 8. 이동 설치 | 카메라를 이동하고 [ROI 편집](DASHBOARD.md) 후 재실행합니다 | 실제 프레임에서 새 보호 구역 분류와 경고 확인 |

가상 시연은 `./scripts/run_mock.sh --scenario tour --dashboard --realtime --stay-open`로 실행합니다. `--scenario`에 `roi1`, `roi2`, `critical`, `dog`, `multi`, `dropout`를 지정해 상황별로 반복합니다. 저장 영상과 Mock은 화면에 각각 표기됩니다.

개 영상 테스트 데이터는 직접 촬영한 영상이나 사용 조건에 맞는 영상을 사용합니다. 저장 영상에서 출력 장치를 연결하면 입력 재생 시간에 맞춰 처리합니다. 영상 파일과 카메라 구도가 다르면 각 입력의 ROI 파일을 `--roi-file`로 따로 지정합니다.
