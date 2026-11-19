# 오프라인 큐와 WISE-PaaS

현장의 판단·출력·SQLite 기록은 HTTP 동기화와 독립적으로 실행됩니다. `--sync`가 켜진 이벤트는 SQLite에 영속 큐 항목으로 생성됩니다. 수신기가 성공을 반환하면 전송 상태를 변경하며, 실패하면 증가하는 백오프 간격으로 재시도합니다. 타임아웃 뒤에도 수신기가 이미 기록했을 수 있으므로 이벤트 UUID를 본문과 `Idempotency-Key`에 같이 전송합니다. 수신기는 이 ID로 중복 제거해야 합니다. 이벤트 보존 정책은 오래된 미전송 항목에도 적용됩니다.

`HttpCloud`는 사용자 지정 HTTPS 게이트웨이의 JSON POST 계약입니다. 이벤트와 장치 응답을 보낼 수 있고 영상과 로컬 파일 경로는 전송 대상에서 제외됩니다. `SITEGUARD_CLOUD_URL`과 `SITEGUARD_CLOUD_TOKEN`은 `.env` 또는 실행 환경에서 읽습니다.

Advantech의 WISE-IoTSuite/DataHub는 프로젝트·노드를 만들고 Node ID, Credential Key, DCCS API URL을 받아 Edge SDK를 구성하는 절차를 제공합니다. 실제 노드의 태그와 스키마가 정해지면 SiteGuard JSON을 태그/이벤트로 매핑하는 게이트웨이 또는 새 어댑터를 연결합니다. 테넌트가 준비될 때까지 아래 Mock 수신기로 확인할 수 있습니다. [Advantech DataHub 공식 문서](https://docs.wise-paas.advantech.com/en/Guides_and_API_References/ApplicationServices/DataHub/1586157244243121667/v2.1.3)

~~~bash
# 터미널 1. 먼저 수신기를 끈 상태에서 터미널 2를 시작하고, 잠시 후 이 명령을 실행
python3 tools/mock_cloud.py --port 8770

# 터미널 2
SITEGUARD_CLOUD_URL=http://127.0.0.1:8770/events ./scripts/run_mock.sh \
  --sync --dashboard --realtime --stay-open

# 저장된 고유 이벤트 수
curl http://127.0.0.1:8770/health
~~~

대시보드에서 offline 중에 `pending`인 이벤트를 확인하고, 수신기를 띄운 뒤 `sent`와 Mock 수신기 저장 수를 비교합니다. 수신기에 같은 UUID를 재전송해도 저장 수가 1만 증가해야 합니다.
