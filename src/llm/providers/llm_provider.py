from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Optional


class LLMProviderError(RuntimeError):
    """Provider 호출 실패를 상위 LLMService에 전달하기 위한 공통 예외."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        code: str = "PROVIDER_ERROR",
        retryable: bool = False,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable
        self.status_code = status_code


class BaseLLMProvider(ABC):
    provider_name: str = "unknown"

    def __init__(
        self,
        ctx: Any,
        model: str,
        *,
        timeout_seconds: int = 120,
    ) -> None:
        if not model or not model.strip():
            raise ValueError("model must not be empty")

        self.ctx = ctx
        self.model = model.strip()
        self.timeout_seconds = int(timeout_seconds)

    @abstractmethod
    async def generate(self, prompt: str, **options: Any) -> str:
        """완성된 문자열 프롬프트를 전달하고 최종 텍스트를 반환한다."""
        raise NotImplementedError

    async def stream(self, prompt: str, **options: Any) -> AsyncIterator[str]:
        """스트리밍 미지원 Provider의 기본 구현."""
        yield await self.generate(prompt, **options)

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

    async def close(self) -> None:
        """필요한 Provider만 오버라이드한다."""
        return None

    def _require_prompt(self, prompt: str) -> str:
        normalized = (prompt or "").strip()
        if not normalized:
            raise ValueError("prompt must not be empty")
        return normalized

    def _require_output(self, output: Optional[str]) -> str:
        normalized = (output or "").strip()
        if not normalized:
            raise LLMProviderError(
                "LLM provider returned an empty response",
                provider=self.provider_name,
                code="EMPTY_RESPONSE",
                retryable=True,
            )
        return normalized

    def _max_output_tokens(self, options: dict[str, Any]) -> Optional[int]:
        value = options.get("max_output_tokens")
        if value is None:
            value = options.get("max_tokens")
        if value is None:
            value = options.get("num_predict")
        return int(value) if value is not None else None

    def _log(self, level: str, message: str) -> None:

        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)
        if not callable(method):
            return

        try:
            method(message)
        except TypeError:
            method("LLM", message)
