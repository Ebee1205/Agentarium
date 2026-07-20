from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from .llm_provider import BaseLLMProvider, LLMProviderError


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(
        self,
        ctx: Any,
        model: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        project: Optional[str] = None,
        timeout_seconds: int = 120,
        max_retries: int = 2,
    ) -> None:
        super().__init__(ctx, model, timeout_seconds=timeout_seconds)

        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_api_key:
            raise ValueError("OPENAI_API_KEY is required")

        client_options: dict[str, Any] = {
            "api_key": resolved_api_key,
            "timeout": self.timeout_seconds,
            "max_retries": max_retries,
        }
        if base_url:
            client_options["base_url"] = base_url.rstrip("/")
        if organization:
            client_options["organization"] = organization
        if project:
            client_options["project"] = project

        self._client = AsyncOpenAI(**client_options)

    async def generate(self, prompt: str, **options: Any) -> str:
        prompt = self._require_prompt(prompt)
        payload = self._build_payload(prompt, options=options, stream=False)

        try:
            response = await self._client.responses.create(**payload)
            return self._require_output(response.output_text)
        except Exception as exc:
            raise self._map_error(exc) from exc

    async def stream(self, prompt: str, **options: Any) -> AsyncIterator[str]:
        prompt = self._require_prompt(prompt)
        payload = self._build_payload(prompt, options=options, stream=True)

        try:
            stream = await self._client.responses.create(**payload)
            async for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    if delta:
                        yield delta
                elif event_type == "error":
                    error = getattr(event, "error", None)
                    raise LLMProviderError(
                        f"OpenAI stream error: {error}",
                        provider=self.provider_name,
                        code="PROVIDER_ERROR",
                        retryable=True,
                    )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc) from exc

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.close()

    def _build_payload(
        self,
        prompt: str,
        *,
        options: dict[str, Any],
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "stream": stream,
            # 서버 측 대화 상태는 현재 DOQ가 직접 관리하므로 기본값을 false로 둔다.
            "store": bool(options.get("store", False)),
        }

        for key in ("temperature", "top_p"):
            if key in options and options[key] is not None:
                payload[key] = options[key]

        max_output_tokens = self._max_output_tokens(options)
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens

        if options.get("instructions"):
            payload["instructions"] = options["instructions"]
        if isinstance(options.get("metadata"), dict):
            payload["metadata"] = options["metadata"]

        reasoning = options.get("reasoning")
        reasoning_effort = options.get("reasoning_effort")
        if isinstance(reasoning, dict):
            payload["reasoning"] = reasoning
        elif reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}

        response_schema = options.get("response_schema")
        response_format = options.get("response_format")
        if isinstance(response_schema, dict):
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": options.get("schema_name", "structured_response"),
                    "schema": response_schema,
                    "strict": bool(options.get("strict_schema", True)),
                }
            }
        elif response_format in {"json", "json_object"}:
            payload["text"] = {"format": {"type": "json_object"}}

        return payload

    def _map_error(self, exc: Exception) -> LLMProviderError:
        if isinstance(exc, LLMProviderError):
            return exc
        if isinstance(exc, APITimeoutError):
            return LLMProviderError(
                "OpenAI request timed out",
                provider=self.provider_name,
                code="TIMEOUT",
                retryable=True,
            )
        if isinstance(exc, APIConnectionError):
            return LLMProviderError(
                f"Unable to connect to OpenAI: {exc}",
                provider=self.provider_name,
                code="CONNECTION_ERROR",
                retryable=True,
            )
        if isinstance(exc, RateLimitError):
            return LLMProviderError(
                str(exc),
                provider=self.provider_name,
                code="RATE_LIMITED",
                retryable=True,
                status_code=429,
            )
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            return LLMProviderError(
                str(exc),
                provider=self.provider_name,
                code="AUTHENTICATION_ERROR",
                retryable=False,
                status_code=getattr(exc, "status_code", None),
            )
        if isinstance(exc, NotFoundError):
            return LLMProviderError(
                str(exc),
                provider=self.provider_name,
                code="MODEL_NOT_FOUND",
                retryable=False,
                status_code=404,
            )
        if isinstance(exc, BadRequestError):
            return LLMProviderError(
                str(exc),
                provider=self.provider_name,
                code="BAD_REQUEST",
                retryable=False,
                status_code=400,
            )
        if isinstance(exc, APIStatusError):
            status = int(getattr(exc, "status_code", 0) or 0)
            return LLMProviderError(
                str(exc),
                provider=self.provider_name,
                code="PROVIDER_UNAVAILABLE" if status >= 500 else "PROVIDER_ERROR",
                retryable=status >= 500,
                status_code=status or None,
            )

        return LLMProviderError(
            f"OpenAI request failed: {exc}",
            provider=self.provider_name,
            code="PROVIDER_ERROR",
            retryable=True,
        )
