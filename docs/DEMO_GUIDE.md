# 강의실 시연

공구를 올린 책상을 기준으로 바닥에 초록(ROI 1 통로), 노랑(ROI 2 자재 인접), 빨강(ROI 3 핵심 보호) 테이프를 붙입니다. 삼각대를 고정하고 먼 구역의 발과 테이프 모서리까지 한 화면에 담습니다. 낮은 가림막 근처에서도 사람이 경계를 넘은 뒤 신발이 화면에 잡히도록 카메라 각도를 잡습니다.

## 실시간 카메라

~~~bash
./scripts/run_camera.sh --camera-index 0 --dry-run --roi-file config/roi.local.classroom.json
~~~

[대시보드](http://127.0.0.1:8765)에서 `편집`을 눌러 각 ROI를 선택합니다. 예시 꼭짓점을 지우고 카메라 화면에서 실제 테이프 모서리를 순서대로 찍은 다음 세 구역을 저장합니다. 옆으로 이어진 테이프는 공유 경계가 맞닿도록, 둘러싼 테이프는 실제 안쪽 윤곽에 맞춰 그립니다. 겹친 지점과 공유 경계에서는 높은 단계가 우선합니다. 추론 모델은 사람·개를 검출하고, 판정은 바운딩 박스의 하단 중앙점과 저장한 다각형으로 계산합니다. 카메라 위치나 구도가 바뀌면 다시 보정합니다.

프리뷰에서 발 기준점과 ROI 번호가 맞으면 프로세스를 종료하고 펌웨어를 올린 Arduino와 출력 장치를 연결합니다.

~~~bash
./scripts/run_camera.sh --camera-index 0 --roi-file config/roi.local.classroom.json \
    --serial-port /dev/ttyACM0 --record --benchmark
~~~

## 촬영 영상에서 AI 결과 MP4 만들기

카메라와 같은 구도의 원본 영상을 사용합니다. 다른 카메라로 촬영했으면 그 영상으로 ROI를 새로 잡습니다. 처음에는 아래 명령에서 `--output-video ...`를 빼고 `--dashboard --realtime --stay-open`을 추가한 뒤, 대시보드에서 보이는 테이프를 기준으로 설정 파일을 저장합니다. 준비된 YOLO 가중치가 필요합니다.

~~~bash
SITEGUARD_PYTHON=.venv-pc/bin/python ./scripts/run_video.sh /path/to/classroom.mp4 --config config/classroom-video.yaml \
    --device cuda:0 --roi-file config/roi.local.classroom-video.json \
    --output-video data/classroom-annotated.mp4 --dry-run --benchmark
~~~

`--device cuda:0`은 CUDA가 동작하는 YOLO 환경에 사용합니다. PC CPU 예행 연습에는 README의 설치 절차와 `--device cpu`를 사용합니다. Jetson Nano의 기본 라이브 백엔드는 SSD-MobileNet-v2입니다. 같은 장비에서 녹화 영상을 SSD GPU로 처리하려면 `SITEGUARD_PYTHON=.venv-jetson/bin/python`과 `--config config/jetson.yaml --dry-run`을 지정합니다. YOLO용 입력 크기 640은 SSD 해상도를 바꾸지 않습니다.

결과에는 입력 프레임 위에 ROI 윤곽, PERSON/ANIMAL (DOG), 추적 ID, 발 기준점, ROI 2 체류 시간, 경고와 해제가 표시됩니다. AVI/MP4 입력을 원본의 명목 FPS로 MP4에 기록하고 오디오 트랙은 생략합니다. 스마트폰 영상의 프레임 간격이 가변적이면 정확한 재생 시각을 위해 먼저 고정 FPS 영상으로 변환합니다. 실제 Arduino 출력 또는 결과 MP4에는 저장된 ROI 파일이 필요합니다.

## 장면별 확인

| 장면 | 준비와 실행 | 성공 조건 |
| --- | --- | --- |
| 1. 구성 소개 | 카메라, 컴퓨터, Arduino, LED·스피커와 공구 책상을 보여줍니다 | 초기 화면에 세 구역 표시 |
| 2. ROI 1 정상 통행 | 초록 통로에만 머문 채 지나갑니다 | PERSON과 ID, ROI 1 표시, LED·음향 OFF |
| 3. ROI 2 장기 체류 | 노랑 구역의 중앙에서 6–7초간 멈춥니다 | 기본 5초 체류 후 1차 경고, LED·음성, 이벤트 기록 |
| 4. ROI 3 핵심 구역 진입 | 1차 경고 후 빨강 구역에 들어가 두 번 이상 검출되도록 발이 보이는 곳에 잠시 섭니다. 나오면서 ROI 2도 벗어나 2초 정도 화면 안에 머뭅니다 | 상위 경고 및 `critical`, 보호 구역 이탈 유지 뒤 `cleared`와 출력 OFF |
| 5. 동물 접근 | 실제 개 영상의 구도에 맞춰 별도 ROI로 재생합니다 | 저장 영상 표기, 개 검출과 ID, ROI 정책 및 비음성 명령 |
| 6. 오프라인과 재전송 | [클라우드 수신기](CLOUD.md)를 끄고 이벤트를 만든 뒤 다시 연결합니다 | 로컬 경고와 기록, 복구 후 `sent` |
| 7. 야간 IR | IR 지원 카메라·조명으로 세팅하고 `--record`를 켭니다 | 실제 IR에서 검출과 LED, 이벤트 클립 확인 |
| 8. 이동 설치 | 카메라를 옮겨 ROI를 새로 저장한 뒤 진입합니다 | 새 좌표에서 분류와 경고 확인 |

가상 시연은 `./scripts/run_mock.sh --scenario tour --dashboard --realtime --stay-open`로 실행합니다. `--scenario`에 `roi1`, `roi2`, `critical`, `dog`, `multi`, `dropout`를 지정해 상황별로 반복합니다. 저장 영상과 Mock은 화면에 각각 표기됩니다.

회의 자료처럼 전체 동선과 장치 근접 장면은 스마트폰으로 따로 촬영하고, 대시보드 화면 녹화나 추론 MP4를 함께 확보합니다. 장치가 연결된 저장 영상은 입력 시간에 맞춰 처리합니다.
