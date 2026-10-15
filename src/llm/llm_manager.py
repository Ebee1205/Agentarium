from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any, Optional

from src.llm.providers.llm_provider import (
    BaseLLMProvider,
    LLMProviderError,
)
from src.llm.providers.ollama_provider import OllamaProvider
from src.llm.providers.mock_provider import MockLLMProvider

# 실제 외부 Provider를 활성화할 때 import의 주석을 해제합니다.
# from src.llm.providers.gemini_provider import GeminiProvider
# from src.llm.providers.openai_provider import OpenAIProvider


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


class LLMManager:
    """
    LLM 호출을 조정하는 공통 매니저.

    담당 역할:
    - AppContext에 등록된 LLM 설정 조회
    - Provider 생성 및 생명주기 관리
    - 프롬프트 조합과 placeholder 치환
    - 일반 텍스트 및 JSON 응답 생성
    - RAGManager 검색 결과를 포함한 응답 생성

    담당하지 않는 역할:
    - 계약 단계 판별
    - 사용자 응답 분류
    - 프롬프트 시나리오 선택
    - 세션 및 DB 상태 갱신

    위 업무들은 각각의 도메인 Service에서 처리하고 이 매니저의
    generate() 또는 generate_json()을 호출하도록 구성합니다.
    """

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self._validate_context()

        self.config = self.ctx.cfg.llm
        self.rag_manager = getattr(self.ctx, "rag_manager", None)

        self.llm_provider: BaseLLMProvider = self._create_provider()

    def _validate_context(self) -> None:
        if not getattr(self.ctx, "cfg", None):
            raise ValueError("AppContext config is not loaded")

        if not getattr(self.ctx.cfg, "llm", None):
            raise ValueError("LLM config is not registered in AppContext")

    def _create_provider(self) -> BaseLLMProvider:
        """
        AppContext의 ``cfg.llm.provider`` 값으로 Provider를 선택합니다.

        현재 활성 Provider:
        - ``ollama``: 기본값, 실제 Ollama 서버 호출
        - ``mock``: 네트워크 호출 없이 프롬프트·이벤트 흐름 검증

        Gemini/OpenAI는 구현 파일만 유지하고, 실제 활성화 시 아래 주석
        구간을 해제하도록 둡니다.
        """
        provider_name = str(
            getattr(self.config, "provider", "ollama") or "ollama"
        ).strip().lower()
        model = str(getattr(self.config, "model", "") or "").strip()
        base_url = getattr(self.config, "base_url", None)
        timeout_seconds = int(
            getattr(self.config, "timeout_seconds", None) or 120
        )
        api_key_env = getattr(self.config, "api_key_env", None)

        # 테스트 환경: 실제 LLM이나 네트워크를 사용하지 않습니다.
        if provider_name == "mock":
            return MockLLMProvider(
                ctx=self.ctx,
                model=model or "mock-llm",
                timeout_seconds=timeout_seconds,
            )

        # 기본 Provider: Ollama
        if provider_name in {"", "ollama"}:
            return OllamaProvider(
                ctx=self.ctx,
                model=model,
                base_url=base_url
                or os.getenv(
                    "OLLAMA_BASE_URL",
                    "http://127.0.0.1:11434",
                ),
                timeout_seconds=timeout_seconds,
                api_key=self._get_env_value(
                    api_key_env or "OLLAMA_API_KEY"
                ),
            )

        # Gemini 활성화 예시
        # if provider_name == "gemini":
        #     return GeminiProvider(
        #         ctx=self.ctx,
        #         model=model,
        #         api_key=self._get_required_env_value(
        #             api_key_env or "GEMINI_API_KEY"
        #         ),
        #         base_url=base_url,
        #         timeout_seconds=timeout_seconds,
        #     )

        # OpenAI 활성화 예시
        # if provider_name == "openai":
        #     return OpenAIProvider(
        #         ctx=self.ctx,
        #         model=model,
        #         api_key=self._get_required_env_value(
        #             api_key_env or "OPENAI_API_KEY"
        #         ),
        #         base_url=base_url,
        #         timeout_seconds=timeout_seconds,
        #     )

        raise ValueError(
            f"Unsupported LLM provider: {provider_name}. "
            "Currently enabled providers are 'ollama' and 'mock'."
        )

    async def generate(
        self,
        prompt: str | Sequence[str],
        *,
        placeholders: Optional[dict[str, Any]] = None,
        **options: Any,
    ) -> str:
        """프롬프트를 합성하고 Provider의 최종 문자열 응답을 반환합니다."""
        final_prompt = self.compose_prompt(
            prompt,
            placeholders=placeholders,
        )

        try:
            return await self.llm_provider.generate(
                final_prompt,
                **options,
            )
        except LLMProviderError as exc:
            self._log_provider_error(exc)
            raise

    async def generate_json(
        self,
        prompt: str | Sequence[str],
        *,
        placeholders: Optional[dict[str, Any]] = None,
        response_schema: Optional[dict[str, Any]] = None,
        **options: Any,
    ) -> dict[str, Any] | list[Any]:
        """
        JSON 응답이 필요한 공통 작업에서 사용합니다.

        Provider가 structured output을 지원하면 response_schema가 전달되고,
        최종 응답은 공통 JSON 파서로 검증합니다.
        """
        response_text = await self.generate(
            prompt,
            placeholders=placeholders,
            response_format="json",
            response_schema=response_schema,
            **options,
        )
        return self._parse_json_response(response_text)

    async def stream(
        self,
        prompt: str | Sequence[str],
        *,
        placeholders: Optional[dict[str, Any]] = None,
        **options: Any,
    ) -> AsyncIterator[str]:
        """Provider의 스트리밍 응답을 그대로 전달합니다."""
        final_prompt = self.compose_prompt(
            prompt,
            placeholders=placeholders,
        )

        try:
            async for chunk in self.llm_provider.stream(
                final_prompt,
                **options,
            ):
                yield chunk
        except LLMProviderError as exc:
            self._log_provider_error(exc)
            raise

    async def rag_generate(
        self,
        query: str,
        *,
        prompt_template: Optional[str] = None,
        top_k: int = 3,
        placeholders: Optional[dict[str, Any]] = None,
        **options: Any,
    ) -> str:
        """RAG 검색 결과와 질의를 합쳐 LLM 응답을 생성합니다."""
        context = await self.retrieve_context(query, top_k=top_k)

        template = prompt_template or (
            "다음 참고 문서와 사용자 질문을 바탕으로 답변하세요.\n\n"
            "[참고 문서]\n{{context}}\n\n"
            "[사용자 질문]\n{{query}}\n\n"
            "[답변]"
        )

        merged_placeholders = {
            **(placeholders or {}),
            "context": context,
            "query": query,
        }

        return await self.generate(
            template,
            placeholders=merged_placeholders,
            **options,
        )

    async def retrieve_context(
        self,
        query: str,
        *,
        top_k: int = 3,
    ) -> str:
        """AppContext에 등록된 RAGManager에서 문자열 컨텍스트를 가져옵니다."""
        if self.rag_manager is None:
            self._log(
                "warning",
                "[RAG] RAGManager is not registered in AppContext",
            )
            return ""

        return await self.rag_manager.asearch_text(
            query,
            k=top_k,
        )

    def compose_prompt(
        self,
        prompt: str | Sequence[str],
        *,
        placeholders: Optional[dict[str, Any]] = None,
    ) -> str:
        """문자열 또는 문자열 목록을 하나의 최종 프롬프트로 합성합니다."""
        if isinstance(prompt, str):
            return self._render_placeholders(prompt, placeholders).strip()

        rendered = [
            self._render_placeholders(str(item), placeholders).strip()
            for item in prompt
            if item is not None and str(item).strip()
        ]
        return "\n\n".join(rendered)

    async def health_check(self) -> bool:
        return await self.llm_provider.health_check()

    async def close(self) -> None:
        await self.llm_provider.close()

    @property
    def provider_name(self) -> str:
        return self.llm_provider.provider_name

    @property
    def model_name(self) -> str:
        return self.llm_provider.model

    def _render_placeholders(
        self,
        text: str,
        placeholders: Optional[dict[str, Any]],
    ) -> str:
        if not placeholders:
            return text

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in placeholders:
                return match.group(0)
            return self._stringify(placeholders[key])

        return _PLACEHOLDER_RE.sub(replace, text)

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        return repr(value)

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any] | list[Any]:
        normalized = (text or "").strip()
        if not normalized:
            raise ValueError("LLM returned an empty JSON response")

        fenced_match = re.search(
            r"```(?:json)?\s*(.*?)\s*```",
            normalized,
            re.DOTALL | re.IGNORECASE,
        )
        json_text = fenced_match.group(1) if fenced_match else normalized

        result = json.loads(json_text)
        if not isinstance(result, (dict, list)):
            raise ValueError("LLM JSON response must be an object or array")
        return result

    @staticmethod
    def _get_env_value(name: Optional[str]) -> Optional[str]:
        return os.getenv(name) if name else None

    @staticmethod
    def _get_required_env_value(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise ValueError(f"Required environment variable is missing: {name}")
        return value

    def _log_provider_error(self, exc: LLMProviderError) -> None:
        self._log(
            "error",
            (
                f"[LLM] provider={exc.provider} code={exc.code} "
                f"retryable={exc.retryable} error={exc}"
            ),
        )

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)
        if not callable(method):
            return

        try:
            method(message)
        except TypeError:
            method("LLM", message)