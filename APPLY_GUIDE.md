# ATM Terrarium MVP 적용 안내

이 디렉터리는 `Ebee1205/Agentarium` 저장소 루트에 덮어쓰기 위한 패치입니다.

## 적용

```bash
cp -R atm-terrarium-patch/src ./
cp -R atm-terrarium-patch/examples ./
```

또는 ZIP을 저장소 루트에서 풀고 동일 경로의 파일을 덮어씁니다.

## 실행

```bash
mkdir -p logs
python -m src.atm_web_server
```

기본 주소:

- WebSocket: `ws://localhost:9571/ws/terrarium/atm-demo`
- 현재 상태: `GET /api/v1/terrarium/atm-demo`
- 시작: `POST /api/v1/terrarium/atm-demo/start`
- 수동 Tick: `POST /api/v1/terrarium/atm-demo/tick`
- 이벤트: `GET /api/v1/terrarium/atm-demo/events`

`examples/terrarium_client.html`을 브라우저로 열면 시작·일시 정지·Tick 실행과 타임라인 확인이 가능합니다.

## 현재 MVP 특성

- 데이터는 프로세스 메모리에 저장됩니다.
- 기본 LLM Provider는 `mock`이며 행동은 결정론적 fallback으로 생성됩니다.
- Redis, RabbitMQ, DB 설정이 없으면 해당 핸들러를 초기화하지 않습니다.
- 실제 Ollama를 연결할 때는 기존 `LLMManager`의 Ollama Provider 주석을 해제하고 설정의 provider를 `ollama`로 변경합니다.
