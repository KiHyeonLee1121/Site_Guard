# SG1 USB Serial 규약

USB CDC, 설정값 기본 115200 baud, ASCII 96바이트 미만의 요청 본문과 LF. 응답은 LF 또는 CRLF입니다. 명령 ID는 대문자 16진수 8자리입니다.

~~~text
SG1 037A00B1 SET_OUTPUT 65 voice_warning
SG1 037A00B1 ACK 65 voice_warning -
SG1 037A00B2 SET_OUTPUT 150 off
SG1 037A00B2 NACK BAD_ARGS
~~~

| 명령 | 매개변수 | 동작 |
| --- | --- | --- |
| SET_OUTPUT | 밝기 0–100, 음향 | LED와 단일 음향 요청 적용 |
| SET_LED | 밝기 0–100 | LED만 변경 |
| PLAY_SOUND | 음향 이름 | 지정된 트랙을 트리거 |
| STOP_SOUND | 없음 | 음향 STOP 트리거 |
| ALL_OFF | 없음 | LED 0, STOP 트리거 |
| GET_STATUS / PING | 없음 | LED·음향·PIR 반환 |

음향 이름은 `off`, `voice_warning`, `voice_critical`, `tone_warning`, `tone_critical`입니다. `ACK <밝기> <펌웨어 음향 상태> <PIR>`에서 PIR은 0, 1, 미연결 `-`입니다. ACK는 명령 파싱과 펌웨어 상태를 나타냅니다. 음향 전환 시 STOP 펄스와 인터록이 끝나 재생 핀을 구동하기 전까지 ACK가 `off`일 수 있습니다. 실제 광량과 스피커 재생 여부는 장비에서 확인합니다.

기본 ACK 대기 350ms, 추가 재전송 2회입니다. 동일 ID와 바이트로 재전송합니다. 펌웨어는 가장 최근 성공 요청의 ID와 내용을 기억합니다. 동일 요청은 상태만 반환하며 같은 ID의 다른 내용에는 `ID_REUSED`를 반환합니다. 오류는 재연결을 시도하고 연결 초기화 후 LED가 여전히 필요하면 복구합니다. 이미 시도한 재생은 재연결 과정에서 반복 트리거하지 않습니다.

Jetson은 기본 750ms마다 제어 또는 상태 명령을 보냅니다. 메인 분석 진행 신호가 끊기면 통신 가능 시 출력을 끕니다. Arduino는 유효 명령이 3초 동안 오지 않으면 LED를 끄고 STOP을 보냅니다. 펌웨어는 음향 재생 시작 4.5초 후 STOP을 보내므로 외부 플레이어가 STOP 입력을 지원해야 합니다.
