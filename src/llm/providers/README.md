# AppContext 연동 버전

## 배치 위치

```text
src/service/llm/llm_manager.py
src/service/llm/rag_manager.py
src/service/llm/providers/*
src/app_context.py
```

## 초기화 순서

```python
ctx.load_config("src/service/conf/doq_be.local.cfg.json")
ctx._init_logger()
ctx._init_rag()
ctx._init_llms()
```

`LLMManager`에는 `ctx`만 전달합니다.

```python
self.llm_manager = LLMManager(ctx=self)
```

`LLMManager`는 다음 정보를 사용합니다.

- `ctx.cfg.llm`: provider, model, base_url, timeout_seconds, api_key_env
- `ctx.rag_manager`: FAISS 기반 RAGManager
- `ctx.log`: 공용 로거

API 키는 JSON 설정 파일에 넣지 않고 환경변수로 등록합니다.

```bash
export GEMINI_API_KEY="..."
export OPENAI_API_KEY="..."
```

Gemini 설정 예시:

```json
"llm": {
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "base_url": null,
  "timeout_seconds": 120,
  "api_key_env": "GEMINI_API_KEY"
}
```

OpenAI 설정 예시:

```json
"llm": {
  "provider": "openai",
  "model": "gpt-5-mini",
  "base_url": null,
  "timeout_seconds": 120,
  "api_key_env": "OPENAI_API_KEY"
}
```