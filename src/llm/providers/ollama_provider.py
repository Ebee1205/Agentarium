from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Optional

import httpx

from .llm_provider import BaseLLMProvider, LLMProviderError


class OllamaProvider(BaseLLMProvider):
    provider_name = "ollama"

    def __init__(
        self,
        ctx: Any,
        model: str,
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 120,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__(ctx, model, timeout_seconds=timeout_seconds)

        normalized_url = base_url.rstrip("/")
        if normalized_url.endswith("/api"):
            normalized_url = normalized_url[:-4]

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self.base_url = normalized_url
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    async def generate(self, prompt: str, **options: Any) -> str:
        prompt = self._require_prompt(prompt)
        payload = self._build_payload(prompt, stream=False, options=options)

        try:
            response = await self._client.post("/api/generate", json=payload)
            self._raise_for_status(response)

            data = response.json()
            if data.get("error"):
                raise LLMProviderError(
                    str(data["error"]),
                    provider=self.provider_name,
                    code="PROVIDER_ERROR",
                    retryable=True,
                )

            return self._require_output(data.get("response"))

        except LLMProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                "Ollama request timed out",
                provider=self.provider_name,
                code="TIMEOUT",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"Unable to connect to Ollama: {exc}",
                provider=self.provider_name,
                code="CONNECTION_ERROR",
                retryable=True,
            ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError(
                f"Invalid response from Ollama: {exc}",
                provider=self.provider_name,
                code="INVALID_RESPONSE",
                retryable=True,
            ) from exc

    async def stream(self, prompt: str, **options: Any) -> AsyncIterator[str]:
        prompt = self._require_prompt(prompt)
        payload = self._build_payload(prompt, stream=True, options=options)

        try:
            async with self._client.stream(
                "POST",
                "/api/generate",
                json=payload,
            ) as response:
                self._raise_for_status(response)

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    data = json.loads(line)
                    if data.get("error"):
                        raise LLMProviderError(
                            str(data["error"]),
                            provider=self.provider_name,
                            code="PROVIDER_ERROR",
                            retryable=True,
                        )

                    delta = data.get("response") or ""
                    if delta:
                        yield delta

        except LLMProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                "Ollama streaming request timed out",
                provider=self.provider_name,
                code="TIMEOUT",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"Ollama streaming connection failed: {exc}",
                provider=self.provider_name,
                code="CONNECTION_ERROR",
                retryable=True,
            ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError(
                f"Invalid Ollama stream payload: {exc}",
                provider=self.provider_name,
                code="INVALID_RESPONSE",
                retryable=True,
            ) from exc

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/api/tags")
            if response.status_code != 200:
                return False

            data = response.json()
            models = data.get("models") or []
            if not models:
                return True

            available_names = {
                item.get("name") or item.get("model")
                for item in models
                if isinstance(item, dict)
            }
            return self.model in available_names
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()

    def _build_payload(
        self,
        prompt: str,
        *,
        stream: bool,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ollama_options: dict[str, Any] = {}

        option_map = {
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
            "repeat_penalty": "repeat_penalty",
            "seed": "seed",
            "num_ctx": "num_ctx",
            "stop": "stop",
        }
        for source_key, target_key in option_map.items():
            if source_key in options and options[source_key] is not None:
                ollama_options[target_key] = options[source_key]

        max_output_tokens = self._max_output_tokens(options)
        if max_output_tokens is not None:
            ollama_options["num_predict"] = max_output_tokens

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }
        if ollama_options:
            payload["options"] = ollama_options

        response_schema = options.get("response_schema")
        response_format = options.get("response_format")
        if isinstance(response_schema, dict):
            payload["format"] = response_schema
        elif response_format in {"json", "json_object"}:
            payload["format"] = "json"

        if options.get("keep_alive") is not None:
            payload["keep_alive"] = options["keep_alive"]
        if options.get("think") is not None:
            payload["think"] = options["think"]

        return payload

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        status = response.status_code
        detail = response.text[:1000]

        if status in {401, 403}:
            code, retryable = "AUTHENTICATION_ERROR", False
        elif status == 404:
            code, retryable = "MODEL_NOT_FOUND", False
        elif status == 429:
            code, retryable = "RATE_LIMITED", True
        elif status >= 500:
            code, retryable = "PROVIDER_UNAVAILABLE", True
        else:
            code, retryable = "BAD_REQUEST", False

        raise LLMProviderError(
            f"Ollama API error {status}: {detail}",
            provider=self.provider_name,
            code=code,
            retryable=retryable,
            status_code=status,
        )