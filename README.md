<a id="readme-top"></a>

<br />

<div align="center">

# Agentarium

### Stateful Multi-Agent Ecosystem Simulation Framework

여러 AI Agent가 하나의 세계에서 기억하고, 관계를 형성하며, 스스로 행동하는 과정을 관찰하기 위한 멀티 Agent 시뮬레이션 프레임워크

</div>

---

## 프로젝트 소개

**Agentarium**은 여러 AI Agent가 하나의 제한된 세계 안에서 각자의 성격, 욕구, 목표, 기억과 관계를 바탕으로 행동하는 과정을 시뮬레이션하는 프로젝트입니다.

현재 구현 중인 **ATM Terrarium**은 Agentarium을 기반으로 한 첫 번째 시뮬레이션 도메인입니다. Agent는 작은 디지털 테라리움 안에서 이동하고, 대화하고, 주변을 관찰하고, 자원을 사용합니다. 각 행동의 결과는 Agent 상태, 다른 Agent와의 관계, 월드 상태에 반영됩니다.

이 프로젝트는 단순히 여러 챗봇을 연결하는 것이 아니라 다음 요소를 분리하여 관리할 수 있는 재사용 가능한 시뮬레이션 구조를 만드는 것을 목표로 합니다.

* Agent 상태 및 행동 결정
* Agent 간 관계와 기억
* 월드 규칙과 자원 변화
* Tick 기반 실행 순서
* LLM Provider 교체
* 시뮬레이션 세션 생명주기
* REST 상태 조회와 WebSocket 이벤트 전달
* 실행 결과 관찰 및 분석

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 핵심 설계 원칙

### Agent는 행동만 결정합니다

Agent Actor는 현재 상태와 관찰 정보를 바탕으로 다음 행동 의도를 반환합니다.

```text
TALK
MOVE
OBSERVE
USE_RESOURCE
WAIT
```

Agent 또는 LLM은 위치, 자원, 감정, 관계 수치를 직접 변경하지 않습니다.

실제 상태 변경은 서버의 World 및 State Manager가 수행합니다.

```text
Agent Actor
    │
    │ 행동 의도 생성
    ▼
Action Validator
    │
    │ 유효성 검증
    ▼
World / State Manager
    │
    │ 결과 계산 및 상태 변경
    ▼
Event / Timeline
```

이 구조를 통해 비정상적인 LLM 출력이 발생하더라도 시뮬레이션 상태 변경 권한을 서버 내부에 유지합니다.

### 상태 변경 책임을 분리합니다

| 구성 요소                 | 책임                        |
| --------------------- | ------------------------- |
| `AgentActor`          | Agent의 다음 행동 의도 생성        |
| `TurnScheduler`       | Tick마다 실행할 Agent 선택       |
| `WorldManager`        | 위치, 경로, 장소, 자원, 시간, 날씨 변경 |
| `AgentStateManager`   | 배고픔, 에너지, 외로움, 감정 변경      |
| `RelationshipManager` | Agent 간 관계 변화 계산          |
| `MemoryManager`       | Agent가 인식한 사건을 기억으로 변환    |
| `TimelineManager`     | 이벤트 저장 및 실시간 전달           |
| `TerrariumSimulation` | 전체 Tick 처리 순서 제어          |

### 상태 조회와 실시간 이벤트를 분리합니다

현재 상태는 REST API로 조회하고, 새롭게 발생한 이벤트는 WebSocket으로 전달합니다.

```text
REST API
- 세션 생성 및 제어
- 현재 상태 조회
- 이전 타임라인 조회

WebSocket
- 신규 이벤트 실시간 전달
```

WebSocket 연결이 끊어진 경우에도 REST API를 이용해 현재 상태를 다시 복원할 수 있습니다.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 주요 기능

### Tick 기반 시뮬레이션

시뮬레이션은 Tick 단위로 진행됩니다.

한 번의 Tick에서는 다음 작업을 순서대로 처리합니다.

```text
1. 실행할 Agent 선택
2. Agent 관찰 정보 생성
3. Mock 또는 LLM을 통한 행동 결정
4. 행동 유효성 검증
5. 행동 결과 계산
6. Agent 및 World 상태 변경
7. 관계와 기억 갱신
8. 이벤트 저장
9. 타임라인 발행
```

현재 MVP는 **Tick마다 Agent 한 명이 행동하는 Round Robin 방식**을 사용합니다.

```text
Tick 1 → Agent A
Tick 2 → Agent B
Tick 3 → Agent C
Tick 4 → Agent A
```

Round Robin 방식은 실행 순서를 재현하기 쉽고, 특정 Agent의 실행이 누락되는 문제를 방지하며, 동시에 여러 LLM 요청이 발생하지 않도록 합니다.

### 자동 및 수동 Tick

* 시뮬레이션이 `RUNNING` 상태이면 설정된 주기에 따라 자동 Tick을 실행합니다.
* `CREATED`, `RUNNING`, `PAUSED` 상태에서는 수동 Tick을 실행할 수 있습니다.
* 자동 Tick과 수동 Tick은 `asyncio.Lock`을 통해 순차적으로 처리합니다.

### 세션 생명주기

시뮬레이션 세션은 다음 상태를 가집니다.

| 상태        | 설명                           |
| --------- | ---------------------------- |
| `CREATED` | 세션은 생성되었지만 자동 실행은 시작되지 않은 상태 |
| `RUNNING` | 자동 Tick이 실행 중인 상태            |
| `PAUSED`  | 상태는 유지되지만 자동 Tick이 중단된 상태    |
| `STOPPED` | 종료된 최종 상태                    |

상태 전이는 다음과 같습니다.

```text
CREATED
   │
   └─ start
       ▼
    RUNNING
      │  │
pause │  │ stop
      ▼  ▼
   PAUSED ──────► STOPPED
      │
      └─ resume
          ▼
       RUNNING
```

종료된 세션은 다시 시작하지 않습니다. 사용자가 새 시뮬레이션을 시작하면 새로운 `simulation_id`를 발급합니다.

### Agent 상태

각 Agent는 다음 정보를 가집니다.

| 구분           | 설명                     |
| ------------ | ---------------------- |
| Identity     | Agent ID와 이름           |
| Personality  | 호기심, 사회성, 공격성 등의 성격    |
| Goal         | 장기적으로 달성하려는 목표         |
| Secret       | 다른 Agent가 직접 알 수 없는 정보 |
| Needs        | 배고픔, 에너지, 외로움          |
| Emotion      | 현재 감정                  |
| Position     | 현재 위치 또는 이동 상태         |
| Relationship | 다른 Agent에 대한 관계        |
| Memory       | 최근 관찰하거나 경험한 사건        |

### 방향성 관계 모델

Agent 간 관계는 방향성을 가진 상태로 관리합니다.

```text
Agent A → Agent B
Agent B → Agent A
```

두 관계는 서로 다른 값을 가질 수 있습니다.

```python
@dataclass
class RelationshipState:
    source_agent_id: str
    target_agent_id: str

    trust: float = 0.0
    affinity: float = 0.0
    fear: float = 0.0
    hostility: float = 0.0
    familiarity: float = 0.0

    last_interaction_tick: int | None = None
```

LLM은 관계 수치를 직접 변경하지 않습니다. 대화, 도움, 위협, 무시와 같은 행동 결과를 기반으로 `RelationshipManager`가 관계 변화를 계산합니다.

### 위치 및 이동 모델

Agent의 위치는 장소에 머무는 상태와 이동 중인 상태로 구분합니다.

```text
LOCATION
TRANSIT
```

장소에 머무는 경우:

```json
{
  "type": "LOCATION",
  "location_id": "kitchen"
}
```

이동 중인 경우:

```json
{
  "type": "TRANSIT",
  "edge_id": "hall-kitchen",
  "from_location_id": "hall",
  "to_location_id": "kitchen",
  "progress": 0.4
}
```

Agent는 이동 시작만 결정합니다. 이후 이동 진행도는 World가 매 Tick 자동으로 갱신합니다.

```text
Tick 10: Hall → Kitchen 이동 시작
Tick 11: progress = 0.33
Tick 12: progress = 0.66
Tick 13: Kitchen 도착
```

현재 MVP에서 이동 중인 Agent는 `OBSERVE`와 `WAIT`만 수행할 수 있습니다.

### Mock 및 Ollama Agent

Agentarium은 동일한 인터페이스를 통해 Mock Agent와 LLM Agent를 교체할 수 있습니다.

#### Mock Agent

Mock 모드는 LLM 실행 환경 없이 다음 항목을 검증하기 위해 사용합니다.

* 세션 생성 및 종료
* Tick 증가
* 상태 전이
* 이벤트 생성
* REST 및 WebSocket 통신
* UI 렌더링
* 테스트 결과 재현

#### Ollama Agent

Ollama 모드에서는 Agent 상태와 관찰 정보를 프롬프트로 전달하고, 구조화된 행동 결과를 생성합니다.

LLM 호출이 실패하거나 유효하지 않은 행동을 반환하면 Mock Agent 행동으로 전환할 수 있습니다.

```text
LLM 행동 결정
  ├─ 성공 → 행동 검증 후 실행
  └─ 실패 → 오류 기록 후 Mock fallback
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 시스템 구조

```text
사용자
  │
  ├─ REST API
  │    ├─ 세션 생성
  │    ├─ 시작·정지·재개·종료
  │    ├─ 현재 상태 조회
  │    └─ 이전 타임라인 조회
  │
  ▼
Simulation Manager
  │
  ├─ Turn Scheduler
  ├─ Agent Actor
  ├─ World Manager
  ├─ Agent State Manager
  ├─ Relationship Manager
  ├─ Memory Manager
  └─ Timeline Manager
          │
          └─ WebSocket
               └─ 신규 이벤트 실시간 전달
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 프로젝트 구조

```text
📦src
 ┣ 📂service
 ┃ ┣ 📂agent
 ┃ ┃ ┣ Agent 상태 모델
 ┃ ┃ ┣ 행동 스키마
 ┃ ┃ ┣ Mock Agent Actor
 ┃ ┃ ┗ LLM Agent Actor
 ┃ ┣ 📂world
 ┃ ┃ ┣ 월드 상태
 ┃ ┃ ┣ 장소 및 이동 경로
 ┃ ┃ ┣ 자원 관리
 ┃ ┃ ┗ 행동 결과 반영
 ┃ ┣ 📂terrarium
 ┃ ┃ ┣ 세션 생성
 ┃ ┃ ┣ 생명주기 관리
 ┃ ┃ ┣ 자동·수동 Tick
 ┃ ┃ ┣ REST API
 ┃ ┃ ┗ WebSocket
 ┃ ┣ 📂timeline
 ┃ ┃ ┣ 이벤트 분류
 ┃ ┃ ┣ 타임라인 변환
 ┃ ┃ ┗ 실시간 이벤트 발행
 ┃ ┗ 📂prompts
 ┃   ┗ Agent 행동 결정 프롬프트
 ┣ 📂conf
 ┃ ┣ 📜atm_web_server.local.cfg.json
 ┃ ┗ 📜atm_web_server.ollama.cfg.json
 ┣ 📂examples
 ┃ ┗ 📜terrarium_client.html
 ┗ 📜atm_web_server.py
```

> 실제 디렉터리 구조는 리팩터링 진행 상황에 따라 변경될 수 있습니다.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## API

### REST API

| Method | Endpoint                                          | 설명           |
| ------ | ------------------------------------------------- | ------------ |
| `POST` | `/api/v1/terrarium`                               | 새 시뮬레이션 생성   |
| `GET`  | `/api/v1/terrarium/{simulation_id}`               | 전체 상태 스냅샷 조회 |
| `GET`  | `/api/v1/terrarium/{simulation_id}/state`         | 현재 상태 조회     |
| `POST` | `/api/v1/terrarium/{simulation_id}/start`         | 시뮬레이션 시작     |
| `POST` | `/api/v1/terrarium/{simulation_id}/pause`         | 일시 정지        |
| `POST` | `/api/v1/terrarium/{simulation_id}/resume`        | 시뮬레이션 재개     |
| `POST` | `/api/v1/terrarium/{simulation_id}/stop`          | 시뮬레이션 종료     |
| `POST` | `/api/v1/terrarium/{simulation_id}/tick`          | 수동 Tick 실행   |
| `GET`  | `/api/v1/terrarium/{simulation_id}/events`        | 내부 이벤트 조회    |
| `GET`  | `/api/v1/terrarium/{simulation_id}/timeline`      | 화면용 타임라인 조회  |
| `POST` | `/api/v1/terrarium/{simulation_id}/interventions` | 관찰자 개입 등록    |

### WebSocket

```text
WS /ws/terrarium/{simulation_id}
```

서버는 다음 이벤트를 발행합니다.

| 이벤트                 | 설명                      |
| ------------------- | ----------------------- |
| `SESSION_CONNECTED` | 연결 직후 현재 상태와 최근 타임라인 전달 |
| `SIMULATION_STATE`  | 상태 변경 이후 최신 상태 전달       |
| `TIMELINE_EVENT`    | 신규 시뮬레이션 이벤트 전달         |
| `TERRARIUM_ERROR`   | 요청 처리 실패 전달             |

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 기술 스택

### Framework

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge\&logo=fastapi\&logoColor=white)
![Asyncio](https://img.shields.io/badge/Asyncio-3776AB?style=for-the-badge\&logo=python\&logoColor=white)

### Language

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge\&logo=python\&logoColor=white)

### AI

![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge\&logo=ollama\&logoColor=white)
![Structured Output](https://img.shields.io/badge/Structured%20Output-4A5568?style=for-the-badge)
![Prompt Engineering](https://img.shields.io/badge/Prompt%20Engineering-5C6BC0?style=for-the-badge)

### Communication

![REST API](https://img.shields.io/badge/REST%20API-005571?style=for-the-badge)
![WebSocket](https://img.shields.io/badge/WebSocket-010101?style=for-the-badge\&logo=socketdotio\&logoColor=white)

### Planned Storage

![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge\&logo=redis\&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-4479A1?style=for-the-badge\&logo=mysql\&logoColor=white)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 시작하기

### 요구 사항

* Python 3.11 이상
* pip
* Ollama를 사용하는 경우 별도의 Ollama 실행 환경과 모델

### 1. 저장소 복제

```bash
git clone https://github.com/Ebee1205/Agentarium.git
cd Agentarium
```

### 2. 가상환경 생성

```bash
python -m venv py_venv
```

가상환경을 활성화합니다.

```bash
# Linux / macOS
source py_venv/bin/activate

# Windows PowerShell
py_venv\Scripts\Activate.ps1
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 로그 디렉터리 생성

```bash
mkdir logs
```

Windows PowerShell에서는 다음 명령을 사용할 수 있습니다.

```powershell
New-Item -ItemType Directory -Force logs
```

### 5. 서버 실행

```bash
python -m src.atm_web_server
```

기본 서버 주소:

```text
http://localhost:9571
```

### 6. 테스트 클라이언트 실행

다음 파일을 브라우저에서 엽니다.

```text
examples/terrarium_client.html
```

다른 API 서버를 사용할 경우 Query Parameter로 주소를 지정할 수 있습니다.

```text
terrarium_client.html?api=http://192.168.0.10:9571
```

기존 세션을 조회할 경우 다음과 같이 `simulation` 값을 전달합니다.

```text
terrarium_client.html?api=http://localhost:9571&simulation={simulation_id}
```

Query Parameter가 없으면 새 세션을 자동으로 생성하지 않고 시작 대기 상태로 진입합니다.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 설정

### Mock Agent

LLM 없이 시뮬레이션 구조를 검증할 때 사용합니다.

```json
{
  "llm": {
    "provider": "mock",
    "model": "atm-mock-agent"
  },
  "terrarium": {
    "use_llm": false,
    "tick_seconds": 3.0
  }
}
```

### Ollama Agent

Ollama 모델을 이용해 Agent 행동을 생성할 때 사용합니다.

```json
{
  "llm": {
    "provider": "ollama",
    "model": "qwen3:8b",
    "base_url": "http://127.0.0.1:11434",
    "timeout_seconds": 120
  },
  "terrarium": {
    "use_llm": true,
    "tick_seconds": 3.0
  }
}
```

설정 파일 이름과 세부 필드는 현재 프로젝트 구성에 맞게 조정해야 합니다.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 테스트

전체 테스트를 실행합니다.

```bash
pytest
```

Python 소스의 문법과 Import 오류를 확인합니다.

```bash
python -m compileall src
```

### 주요 검증 시나리오

다음 흐름을 중심으로 수동 E2E 테스트를 수행합니다.

1. 최초 접속 시 세션이 자동 생성되지 않는지 확인
2. 시작 시 새 `simulation_id`가 발급되는지 확인
3. 시작 후 자동 Tick이 증가하는지 확인
4. 수동 Tick과 자동 Tick이 충돌하지 않는지 확인
5. 일시 정지 중 자동 Tick이 중단되는지 확인
6. 재개 후 자동 Tick이 다시 실행되는지 확인
7. 종료 후 Task와 WebSocket이 정리되는지 확인
8. 다시 시작할 때 새로운 세션이 생성되는지 확인
9. Ollama 실패 시 Mock fallback이 동작하는지 확인

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 현재 제한 사항

### 메모리 기반 상태 관리

현재 시뮬레이션 상태와 이벤트는 주로 서버 프로세스 메모리에 저장됩니다.

따라서 다음 기능은 아직 지원하지 않습니다.

* 서버 재시작 이후 세션 복구
* 다중 Worker 간 상태 공유
* 과거 시뮬레이션 영구 조회
* 장애 발생 이후 자동 복구

### 단일 프로세스 자동 Tick

자동 Tick Task가 웹 서버 프로세스 내부에서 실행되므로, 다중 Worker 환경에서는 동일 세션이 중복 실행되지 않도록 별도의 분산 Lock이 필요합니다.

### LLM 출력 안정성

LLM은 항상 유효한 JSON이나 실행 가능한 행동을 반환하지 않을 수 있습니다.

향후 다음 기능을 보완할 예정입니다.

* JSON Schema 검증
* 출력 정규화
* 행동 재시도
* Timeout 처리
* fallback 사유 기록
* Agent별 호출량 제한
* Prompt Injection 방어

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## 라이선스

Copyright (c) 2026. Ebee1205(wavicle). All rights reserved.

<p align="right">(<a href="#readme-top">back to top</a>)</p>
