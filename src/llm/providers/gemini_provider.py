from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any, Optional

from google import genai
from google.genai import errors, types

from .llm_provider import BaseLLMProvider, LLMProviderError


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(
        self,
        ctx: Any,
        model: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout_seconds: int = 120,
    ) -> None:
        super().__init__(ctx, model, timeout_seconds=timeout_seconds)

        resolved_api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_api_key:
            raise ValueError("GEMINI_API_KEY is required")

        http_options: dict[str, Any] = {}
        if base_url:
            http_options["base_url"] = base_url.rstrip("/")
        if api_version:
            http_options["api_version"] = api_version

        client = genai.Client(
            api_key=resolved_api_key,
            http_options=http_options or None,
        )
        self._client = client.aio

    async def generate(self, prompt: str, **options: Any) -> str:
        prompt = self._require_prompt(prompt)
        config = self._build_config(options)

        try:
            response = await asyncio.wait_for(
                self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                ),
                timeout=self.timeout_seconds,
            )
            return self._require_output(response.text)

        except asyncio.TimeoutError as exc:
            raise LLMProviderError(
                "Gemini request timed out",
                provider=self.provider_name,
                code="TIMEOUT",
                retryable=True,
            ) from exc
        except errors.APIError as exc:
            raise self._map_api_error(exc) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                f"Gemini request failed: {exc}",
                provider=self.provider_name,
                code="PROVIDER_ERROR",
                retryable=True,
            ) from exc

    async def stream(self, prompt: str, **options: Any) -> AsyncIterator[str]:
        prompt = self._require_prompt(prompt)
        config = self._build_config(options)

        try:
            stream = await asyncio.wait_for(
                self._client.models.generate_content_stream(
                    model=self.model,
                    contents=prompt,
                    config=config,
                ),
                timeout=self.timeout_seconds,
            )

            iterator = stream.__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=self.timeout_seconds,
                    )
                except StopAsyncIteration:
                    break

                delta = chunk.text or ""
                if delta:
                    yield delta

        except asyncio.TimeoutError as exc:
            raise LLMProviderError(
                "Gemini streaming request timed out",
                provider=self.provider_name,
                code="TIMEOUT",
                retryable=True,
            ) from exc
        except errors.APIError as exc:
            raise self._map_api_error(exc) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                f"Gemini streaming request failed: {exc}",
                provider=self.provider_name,
                code="PROVIDER_ERROR",
                retryable=True,
            ) from exc

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                self._client.models.list(config={"page_size": 1}),
                timeout=min(self.timeout_seconds, 10),
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()

    def _build_config(self, options: dict[str, Any]) -> types.GenerateContentConfig:
        config: dict[str, Any] = {}

        for key in ("temperature", "top_p", "top_k", "seed"):
            if key in options and options[key] is not None:
                config[key] = options[key]

        max_output_tokens = self._max_output_tokens(options)
        if max_output_tokens is not None:
            config["max_output_tokens"] = max_output_tokens

        stop_sequences = options.get("stop_sequences", options.get("stop"))
        if stop_sequences:
            config["stop_sequences"] = (
                [stop_sequences] if isinstance(stop_sequences, str) else stop_sequences
            )

        if options.get("system_instruction"):
            config["system_instruction"] = options["system_instruction"]

        response_schema = options.get("response_schema")
        response_format = options.get("response_format")
        if isinstance(response_schema, dict):
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = response_schema
        elif response_format in {"json", "json_object"}:
            config["response_mime_type"] = "application/json"

        return types.GenerateContentConfig(**config)

    def _map_api_error(self, exc: errors.APIError) -> LLMProviderError:
        status = int(getattr(exc, "code", 0) or 0)
        message = getattr(exc, "message", None) or str(exc)

        if status in {401, 403}:
            code, retryable = "AUTHENTICATION_ERROR", False
        elif status == 404:
            code, retryable = "MODEL_NOT_FOUND", False
        elif status == 429:
            code, retryable = "RATE_LIMITED", True
        elif status in {408, 504}:
            code, retryable = "TIMEOUT", True
        elif status >= 500:
            code, retryable = "PROVIDER_UNAVAILABLE", True
        else:
            code, retryable = "BAD_REQUEST", False

        return LLMProviderError(
            f"Gemini API error {status}: {message}",
            provider=self.provider_name,
            code=code,
            retryable=retryable,
            status_code=status or None,
        )