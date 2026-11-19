# 3인 협업

| 담당 | 코드 영역 | 공동 확인 |
| --- | --- | --- |
| A · AI/영상 | `vision/`, `models/`, 추론 준비 도구 | 카메라·영상 입력, 클래스 매핑, Nano 모델 성능, 동일 객체 ID 안정성 |
| B · 메인 엔진 | `engine/`, `pipeline.py`, `schemas.py` | ROI와 체류, 상태표, 다중 객체 출력 우선순위, Mock 시연 |
| C · 장치/데이터 | `hardware/`, `firmware/`, `storage/`, `network/` | Serial 호환성, PIR, LED·스피커, 오프라인 기록 및 재전송 |

모듈 경계가 바뀌면 [모듈 계약](MODULE_INTERFACES.md)과 관련 테스트를 함께 수정합니다. 개인 작업 브랜치에서 테스트 후 PR을 만듭니다. 시연 전에 같은 커밋에서 Mock과 실제 장치를 각각 검사합니다.
