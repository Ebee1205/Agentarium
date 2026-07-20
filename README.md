<!-- Improved compatibility of back to top link: See: https://github.com/othneildrew/Best-README-Template/pull/73 -->
<a id="readme-top"></a>
<!--
*** Thanks for checking out the Best-README-Template. If you have a suggestion
*** that would make this better, please fork the repo and create a pull request
*** or simply open an issue with the tag "enhancement".
*** Don't forget to give the project a star!
*** Thanks again! Now go create something AMAZING! :D
-->



<!-- PROJECT SHIELDS -->
<!--
*** I'm using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->

<!-- [![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![project_license][license-shield]][license-url] -->

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h1 align="center">Python Unified Server Architecture</h1>
  <p align="center">
    <em>Modular, Event-Driven Multi-Server Framework</em>
  </p>
</div>


<!-- 프로젝트 소개 -->
## 프로젝트 소개

본 프로젝트는 **AppContext**를 공유하는 단일 코드 베이스 구조를 가진다. 실행 설정과 진입점(Entry Point)에 따라 **Web API Server** 또는 **Middleware Server**로 동작한다.

계층별 설계로 유지보수성과 확장성을 높였다.

| 계층 | 역할 |
| --- | --- |
| **Core & Handler** | 공통 응답 규격 관리 및 DB(SQL, MongoDB), 메시징(RabbitMQ, Redis Stream), WebSocket 연결을 처리한다. |
| **Service** | API-Service-Schema 구조를 기반으로 도메인 로직을 구현한다. |
| **Context** | 환경 설정 로드 및 각 구성 요소의 라이프사이클을 통합 관리한다. |


<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- 주요기능 -->
## 🎯 주요기능

#### 🧠 AI 서비스 인터페이스 (`src/service/ai`)
`service/ai` 모듈은 LLM 및 Python 기반 AI 알고리즘을 유연하게 실행하고 관리할 수 있는 통합 인터페이스를 제공한다.

* **LLM 및 알고리즘 구동**: `llm_manager.py`와 `rag_manager.py`를 사용하여 다양한 AI 알고리즘을 즉시 실행한다.
* **채팅 상태 관리**: `ChatStateManager`를 통해 사용자별 세션과 상호작용 상태를 동적으로 유지한다.
* **프롬프트 관리**: `asset/prompts` 디렉토리에서 시나리오별 프롬프트 체인을 관리하여 응답 정확도를 제어한다.

#### ✅ 이벤트 기반 통신
- RabbitMQ와 WebSocket 기반의 비동기 처리를 통합하여 시스템 간 실시간 메시징을 지원한다.

#### 🛠 서비스 예제 및 즉시 활용 모듈
구조적 이해를 돕기 위한 예제 항목들이 포함되어 있으며, 이는 실제 서비스에 바로 적용할 수 있는 수준으로 구현되어 있다.

* **인증(Auth)**: JWT 기반 사용자 인증 및 권한 관리 로직을 즉시 적용한다.
* **파일 처리(Files)**: 파일 업로드/다운로드 및 관리 인터페이스를 활용하여 데이터 처리 서비스를 구축한다.


<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- 프로젝트 구조 -->
## 프로젝트 구조

```text
📦src
 ┣ 📂core       # 공통 유틸리티 및 응답 규격
 ┣ 📂handler    # 인프라 연결 (DB, RMQ, Redis, WS)
 ┣ 📂service    # 비즈니스 도메인 (AI, Auth, Files, Tag)
 ┃ ┣ 📂ai       # LLM, RAG 로직 및 프롬프트 에셋
 ┃ ┗ 📂conf     # 서버별 JSON 설정 파일
 ┣ 📂sql        # DB 초기화 및 시드 스크립트
 ┗ 📂utils      # 비동기 및 통신 유틸리티
```

설정 파일에 따라 동일한 소스 코드가 서로 다른 성격의 서버로 구동된다.

| 서버 유형 | 실행 파일 | 기반 기술 | 핵심 역할 |
| :--- | :--- | :--- | :--- |
| **Web API** | `src/py_web_server.py` | FastAPI | REST API 제공, CORS 및 전역 예외 처리 |
| **Base** | `src/py_server.py` | FastAPI | AI 모델 초기화 및 기본 시스템 통신 테스트 |
| **Middleware** | `src/py_mw_server.py` | Asyncio | 메시지 소비 |

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- 지원 -->
## 📚 지원

#### Framework
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white) ![Asyncio](https://img.shields.io/badge/Asyncio-232F3E?style=for-the-badge&logo=python&logoColor=white)

#### Language
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)

#### Database
![MySQL](https://img.shields.io/badge/MySQL(SQL)-4479A1?style=for-the-badge&logo=mysql&logoColor=white) ![MongoDB](https://img.shields.io/badge/MongoDB(NoSQL)-47A248?style=for-the-badge&logo=mongodb&logoColor=white) ![Redis](https://img.shields.io/badge/Redis(NoSQL)-DC382D?style=for-the-badge&logo=redis&logoColor=white)

#### Messaging
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white) ![MQTT](https://img.shields.io/badge/MQTT-660066?style=for-the-badge&logo=eclipsemosquitto&logoColor=white) ![Redis Stream](https://img.shields.io/badge/Redis%20Stream-DC382D?style=for-the-badge&logo=redis&logoColor=white) ![WebSocket](https://img.shields.io/badge/WebSocket-010101?style=for-the-badge&logo=socketdotio&logoColor=white)

#### AI/ML
![Google Gemini](https://img.shields.io/badge/Google%20Gemini(LLM)-4285F4?style=for-the-badge&logo=google&logoColor=white) ![RAG Pipeline](https://img.shields.io/badge/RAG-Pipeline-5C6BC0?style=for-the-badge)

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- 시작하기 -->
## 🚀 시작하기

### 1. 로그 및 가상환경 디렉토리 생성
```bash
mkdir logs py_venv
```

### 2. 의존성 설치 (Python 3.11 권장)

```bash
python3.11 -m venv py_venv
source py_venv/bin/activate  # Windows: py_venv\\Scripts\\activate
pip install -r requirements.txt
```

### 3. 환경 설정
src/service/conf 디렉토리 내의 각 서버용 설정 파일을 환경에 맞게 수정한다.
- `py_web_server.local.cfg.json`: Web API Server용 설정
- `py_mw_server.local.cfg.json`: Middleware Server용 설정


### 4. 서버를 실행

```bash
python -m src.py_web_server    # Web API Server (기본 8000 포트)
python -m src.py_mw_server     # Middleware Server (기본 3000 포트)
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- 관련 링크 -->
### 📝 관련 링크

#### 개발 노트

| 구분 | 제목 | 설명 |
| :--- | :--- | :--- |
| **Architecture** | [LLM 인터페이스 설계](https://wavicle.tistory.com/21) | DI/IoC 원칙을 적용한 AI 엔진 교체 가능한 인터페이스 설계 내용 기록 |
| **Case Study** | [방토리: AI 기반 스마트 룸 컨디션 매니저](https://wavicle.tistory.com/32) | |
| **Case Study** | [둥지동지 2.0.0 개발노트](https://wavicle.tistory.com/31) | LLM Classification으로 자연어 구인글을 구조화된 JSON으로 변환하는 파이프라인 적용 사례다. |


#### **주요 프로젝트 저장소**
본 아키텍처가 실제로 적용된 주요 프로젝트 라이브러리

| 구분 | 프로젝트 | 설명 |
| :--- | :--- | :--- |
| **Web API** | [TryAngle BE (트라이앵글)](https://github.com/AT-try-angle/try-angle-server) | FastAPI 기반의 온디바이스 AI 포즈 가이드 서비스용 서버 |
| **Middleware** | [TryAngle MW (트라이앵글)](https://github.com/AT-try-angle/try-angle-server) | 시스템 간 통신 관리 및 실시간 데이터 처리를 위한 미들웨어 서버 |
| **Web API & AI** | [ DOQ (도큐)](https://github.com/AT-Ankoko/doq-server) | LLM 기반의 AI 계약 중재 및 협상 플랫폼 서버 |
| **Web API & AI** | [둥지동지 (DungDong)](https://github.com/GetOurRI/DungDong-BE) | 대학 커뮤니티용 룸메이트 매칭 및 이미지 생성 AI 서버 |
| **Web API & AI** | [방토리  (Bangtori)](https://github.com/gaj-on/Bangtori_AI) | 실시간 데이터 처리를 위한 AI 기반 주거 정보 서비스 서버 |




<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- 라이선스 -->
## 📄 라이선스

Copyright (c) 2025. Ebee1205(wavicle) all rights reserved.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/github_username/repo_name.svg?style=for-the-badge
[contributors-url]: https://github.com/github_username/repo_name/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/github_username/repo_name.svg?style=for-the-badge
[forks-url]: https://github.com/github_username/repo_name/network/members
[stars-shield]: https://img.shields.io/github/stars/github_username/repo_name.svg?style=for-the-badge
[stars-url]: https://github.com/github_username/repo_name/stargazers
[issues-shield]: https://img.shields.io/github/issues/github_username/repo_name.svg?style=for-the-badge
[issues-url]: https://github.com/github_username/repo_name/issues
[license-shield]: https://img.shields.io/github/license/github_username/repo_name.svg?style=for-the-badge
[license-url]: https://github.com/github_username/repo_name/blob/master/LICENSE.txt
