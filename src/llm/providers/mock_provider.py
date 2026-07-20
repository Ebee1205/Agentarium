from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

from .llm_provider import BaseLLMProvider, LLMProviderError


EventHandler = Callable[[str, dict[str, Any]], Any]
ResponseFactory = Callable[[str, dict[str, Any]], str]


@dataclass(frozen=True)
class MockProviderRequest:
    """MockProvider가 받은 최종 프롬프트와 옵션을 보존합니다."""

    sequence: int
    prompt: str
    options: dict[str, Any] = field(default_factory=dict)


class MockLLMProvider(BaseLLMProvider):
    """
    실제 LLM 연결 없이 LLMManager 호출 흐름을 검증하는 Provider 스텁.

    지원 기능:
    - 최종 합성 프롬프트와 옵션 캡처
    - 고정 응답 또는 호출별 응답 시퀀스
    - JSON 응답 자동 생성
    - 스트리밍 청크 시뮬레이션
    - 응답 지연 및 실패 시뮬레이션
    - REQUESTED/PROMPT_CAPTURED/CHUNK/COMPLETED/FAILED 이벤트 발행

    테스트 전용 클래스이므로 운영 Provider의 네트워크 호출은 수행하지 않습니다.
    """

    provider_name = "mock"

    def __init__(
        self,
        ctx: Any,
        model: str = "mock-llm",
        *,
        timeout_seconds: int = 120,
        response: str = "테스트용 Mock LLM 응답입니다.",
        responses: Optional[Sequence[str]] = None,
        response_factory: Optional[ResponseFactory] = None,
        stream_chunks: Optional[Sequence[str]] = None,
        delay_seconds: float = 0.0,
        fail: bool = False,
        fail_code: str = "MOCK_FAILURE",
        retryable: bool = False,
        healthy: bool = True,
        event_handler: Optional[EventHandler] = None,
    ) -> None:
        super().__init__(ctx, model, timeout_seconds=timeout_seconds)

        self.default_response = response
        self.responses = list(responses or [])
        self.response_factory = response_factory
        self.default_stream_chunks = list(stream_chunks or [])
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.fail = bool(fail)
        self.fail_code = fail_code
        self.retryable = bool(retryable)
        self.healthy = bool(healthy)
        self.event_handler = event_handler

        self.requests: list[MockProviderRequest] = []
        self.events: list[dict[str, Any]] = []
        self._call_count = 0

    async def generate(self, prompt: str, **options: Any) -> str:
        prompt = self._require_prompt(prompt)
        request = self._capture_request(prompt, options)

        await self._emit(
            "LLM_REQUESTED",
            request=request,
            mode="generate",
        )
        await self._emit(
            "LLM_PROMPT_CAPTURED",
            request=request,
            prompt=prompt,
            options=dict(options),
        )

        try:
            await self._sleep(options)
            self._raise_mock_failure(options)

            output = self._resolve_response(prompt, options)
            output = self._require_output(output)

            await self._emit(
                "LLM_COMPLETED",
                request=request,
                output=output,
                mode="generate",
            )
            return output

        except Exception as exc:
            await self._emit(
                "LLM_FAILED",
                request=request,
                error_type=type(exc).__name__,
                error=str(exc),
                retryable=getattr(exc, "retryable", False),
            )
            raise

    async def stream(self, prompt: str, **options: Any) -> AsyncIterator[str]:
        prompt = self._require_prompt(prompt)
        request = self._capture_request(prompt, options)

        await self._emit(
            "LLM_REQUESTED",
            request=request,
            mode="stream",
        )
        await self._emit(
            "LLM_PROMPT_CAPTURED",
            request=request,
            prompt=prompt,
            options=dict(options),
        )

        try:
            self._raise_mock_failure(options)
            chunks = self._resolve_stream_chunks(prompt, options)
            chunk_delay = float(
                options.get("mock_chunk_delay_seconds", self.delay_seconds)
            )

            for index, chunk in enumerate(chunks):
                if chunk_delay > 0:
                    await asyncio.sleep(chunk_delay)

                await self._emit(
                    "LLM_CHUNK",
                    request=request,
                    sequence=index,
                    delta=chunk,
                )
                yield chunk

            await self._emit(
                "LLM_COMPLETED",
                request=request,
                output="".join(chunks),
                chunk_count=len(chunks),
                mode="stream",
            )

        except Exception as exc:
            await self._emit(
                "LLM_FAILED",
                request=request,
                error_type=type(exc).__name__,
                error=str(exc),
                retryable=getattr(exc, "retryable", False),
            )
            raise

    async def health_check(self) -> bool:
        await self._emit(
            "LLM_HEALTH_CHECKED",
            healthy=self.healthy,
        )
        return self.healthy

    async def close(self) -> None:
        await self._emit("LLM_PROVIDER_CLOSED")

    @property
    def last_request(self) -> Optional[MockProviderRequest]:
        return self.requests[-1] if self.requests else None

    def clear_history(self) -> None:
        """캡처한 요청과 이벤트 기록을 모두 초기화합니다."""
        self.requests.clear()
        self.events.clear()
        self._call_count = 0

    def _capture_request(
        self,
        prompt: str,
        options: dict[str, Any],
    ) -> MockProviderRequest:
        request = MockProviderRequest(
            sequence=len(self.requests) + 1,
            prompt=prompt,
            options=dict(options),
        )
        self.requests.append(request)
        self._call_count += 1
        return request

    async def _sleep(self, options: dict[str, Any]) -> None:
        delay = float(options.get("mock_delay_seconds", self.delay_seconds))
        if delay > 0:
            await asyncio.sleep(delay)

    def _raise_mock_failure(self, options: dict[str, Any]) -> None:
        should_fail = bool(options.get("mock_fail", self.fail))
        if not should_fail:
            return

        raise LLMProviderError(
            str(options.get("mock_error_message", "Mock provider failure")),
            provider=self.provider_name,
            code=str(options.get("mock_error_code", self.fail_code)),
            retryable=bool(options.get("mock_retryable", self.retryable)),
            status_code=options.get("mock_status_code"),
        )

    def _resolve_response(
        self,
        prompt: str,
        options: dict[str, Any],
    ) -> str:
        direct_response = options.get("mock_response")
        if direct_response is not None:
            return str(direct_response)

        if self.response_factory is not None:
            return str(self.response_factory(prompt, dict(options)))

        if self.responses:
            index = min(self._call_count - 1, len(self.responses) - 1)
            return str(self.responses[index])

        if self._expects_json(options):
            payload = options.get("mock_json_response")
            if payload is None:
                payload = {
                    "mock": True,
                    "provider": self.provider_name,
                    "model": self.model,
                    "message": "테스트용 JSON 응답입니다.",
                    "prompt_preview": prompt[:120],
                }
            return json.dumps(payload, ensure_ascii=False)

        return self.default_response

    def _resolve_stream_chunks(
        self,
        prompt: str,
        options: dict[str, Any],
    ) -> list[str]:
        direct_chunks = options.get("mock_stream_chunks")
        if direct_chunks is not None:
            return [str(item) for item in direct_chunks]

        if self.default_stream_chunks:
            return list(self.default_stream_chunks)

        response = self._resolve_response(prompt, options)
        chunk_size = max(1, int(options.get("mock_chunk_size", 8)))
        return [
            response[index:index + chunk_size]
            for index in range(0, len(response), chunk_size)
        ]

    @staticmethod
    def _expects_json(options: dict[str, Any]) -> bool:
        return (
            isinstance(options.get("response_schema"), dict)
            or options.get("response_format") in {"json", "json_object"}
        )

    async def _emit(self, event_type: str, **payload: Any) -> None:
        """Mock 이벤트를 Provider 내부에 기록하고 선택적으로 외부로 전달합니다."""
        event_payload = {
            "event_type": event_type,
            "provider": self.provider_name,
            "model": self.model,
            **self._normalize_event_payload(payload),
        }
        self.events.append(event_payload)

        self._log(
            "debug",
            "[LLM:MOCK] "
            + json.dumps(event_payload, ensure_ascii=False, default=str),
        )

        if self.event_handler is None:
            return

        result = self.event_handler(event_type, event_payload)
        if hasattr(result, "__await__"):
            await result

    @staticmethod
    def _normalize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, MockProviderRequest):
                normalized[key] = {
                    "sequence": value.sequence,
                    "prompt": value.prompt,
                    "options": value.options,
                }
            else:
                normalized[key] = value
        return normalized