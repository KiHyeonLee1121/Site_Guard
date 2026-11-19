# 모듈 계약

| 모듈 | 입력 | 출력 또는 계약 |
| --- | --- | --- |
| `vision.sources` | 카메라·파일·시나리오 | `Frame(image, width, height, timestamp, captured_at, fixture)`. 이미지 BGR, 원본 픽셀 크기. 라이브 카메라 유휴나 단절 시 `None` |
| `Detector.detect` | `Frame` | `Detection(class_name, confidence, bbox, timestamp)` 리스트. 클래스는 `person` 또는 `dog`, 박스는 XYXY 픽셀 |
| `Tracker.update` | 검출, 기준 시간, 해상도 | `Observation(track_id, detection, visible)`과 만료된 ID 목록 |
| `ROIManager.classify` | 정규화 다각형, 픽셀 박스, 해상도 | 0–3 단계. 0은 구역 외부 |
| `TrackState.update` | 시간, ROI 또는 누락 | 전환 이벤트와 현재 `TrackStatus` |
| `aggregate` | 추적 객체 상태 | 공용 `Output(level, brightness, sound, sound_revision)` |
| `Actuator.submit` / `drain` | 원하는 출력, 음향 재생 여부 | 명령 ID와 비동기 결과 목록 |
| `Database` | 이벤트, 명령, 전송 시각 | 이벤트, 응답, 영상 파일명, 클라우드 재시도 상태 |
| `HttpCloud.send` | 하나의 이벤트 | 확정 수락이면 반환, 실패하면 예외. 수신 측 ID 중복 제거 필요 |

ROI 편집은 `ROIManager.save(payload, expected_revision)`를 사용합니다. 로직용 프레임과 대시보드 오버레이는 같은 원본 해상도를 기준으로 합니다. 추론 모델 변경 시 클래스 목록과 좌표 변환을 Detector에서 보정합니다. 새 Arduino 장치에는 장치 API나 SG1 규약을 유지하는 어댑터를 붙입니다.
