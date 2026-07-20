"""
기존 LLMManager에 적용할 핵심 변경 예시.

기존의 프롬프트 합성, 인젝션 검사, classify_response, rag_generate는 유지하고
실제 HTTP/SDK 호출 블록만 self.llm_provider.generate(...)로 교체한다.
"""

import os
from typing import Any, Optional

from providers import GeminiProvider, LLMProviderError, OllamaProvider, OpenAIProvider


def create_llm_provider(
    ctx: Any,
    *,
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    timeout_seconds: int = 120,
):
    provider = provider.lower().strip()

    if provider == "ollama":
        return OllamaProvider(
            ctx,
            model,
            base_url=base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            timeout_seconds=timeout_seconds,
            api_key=os.getenv("OLLAMA_API_KEY"),
        )

    if provider == "gemini":
        return GeminiProvider(
            ctx,
            model,
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    if provider == "openai":
        return OpenAIProvider(
            ctx,
            model,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    raise ValueError(f"Unsupported provider: {provider}")


async def generate_with_provider(
    manager,
    prompt,
    *,
    placeholders=None,
    **options,
) -> str:
    """기존 LLMManager.generate() 내부에 들어갈 형태의 예시."""
    final_prompt = manager._compose_prompt(prompt, placeholders=placeholders)

    try:
        return await manager.llm_provider.generate(final_prompt, **options)
    except LLMProviderError as exc:
        manager.ctx.log.error(
            f"[LLM] provider={exc.provider} code={exc.code} "
            f"retryable={exc.retryable} error={exc}"
        )

        if exc.code == "MODEL_NOT_FOUND":
            return "죄송합니다. 요청한 AI 모델을 찾을 수 없습니다."
        if exc.code == "RATE_LIMITED":
            return "죄송합니다. 현재 AI 서비스 사용량이 많아 잠시 후 다시 시도해주세요."
        if exc.code == "TIMEOUT":
            return "죄송합니다. AI 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
        if exc.code in {"CONNECTION_ERROR", "PROVIDER_UNAVAILABLE"}:
            return "죄송합니다. AI 서버에 연결할 수 없습니다. 서버 상태를 확인해주세요."
        return "죄송합니다. AI 응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
