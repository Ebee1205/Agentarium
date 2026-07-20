# 파일 구성

## 수정 파일

- `src/app_context.py`
  - `TerrariumConfig` 추가
  - Event/World/Agent/Simulation Manager 등록 필드 추가
  - `_init_terrarium_managers()` 추가
- `src/atm_web_server.py`
  - 미정의 라우터 참조 제거
  - Terrarium Router 등록
  - LLM/Terrarium Manager 초기화
  - Redis/RabbitMQ/DB 선택 초기화
  - 시뮬레이션 및 LLM 종료 처리
  - `/health` 추가

## 추가 파일

- `src/conf/atm_web_server.local.cfg.json`
- `src/conf/atm-event-map.cfg.json`
- `src/service/terrarium/__init__.py`
- `src/service/terrarium/terrarium_schema.py`
- `src/service/terrarium/event_manager.py`
- `src/service/terrarium/world_manager.py`
- `src/service/terrarium/agent_manager.py`
- `src/service/terrarium/simulation_manager.py`
- `src/service/terrarium/terrarium_router.py`
- `src/service/terrarium/prompts/agent_action.txt`
- `examples/terrarium_client.html`
- `tests/test_terrarium_schema.py`
- `APPLY_GUIDE.md`

## WebSocket 이벤트

클라이언트 요청:

- `PING`
- `SIMULATION_START`
- `SIMULATION_PAUSE`
- `SIMULATION_RESUME`
- `SIMULATION_STOP`
- `RUN_TICK`
- `GET_STATE`
- `OBSERVER_INTERVENTION`

서버 발행:

- `SESSION_CONNECTED`
- `SIMULATION_STATE`
- `TIMELINE_EVENT`
- `TERRARIUM_ERROR`
