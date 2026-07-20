from __future__ import annotations

import os
from asyncio import to_thread
from dataclasses import dataclass, field
from typing import Any, Optional

import orjson
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings


@dataclass(frozen=True)
class RetrievedDocument:
    """검색된 문서를 Provider나 도메인에 종속되지 않은 형태로 표현합니다."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None


class RAGManager:
    """
    문서 임베딩, 벡터 인덱스, 유사도 검색을 관리하는 공통 매니저.

    현재 기본 구현:
    - Embedding: OllamaEmbeddings
    - Vector Store: FAISS

    생성 LLM Provider와는 독립적으로 동작합니다. 따라서 답변 생성 Provider를
    Gemini나 OpenAI로 교체해도 RAG 검색 구현은 그대로 사용할 수 있습니다.
    """

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self._validate_context()

        self.config = self.ctx.cfg.rag
        self.chunks_path = self.config.chunks_path
        self.index_path = self.config.index_path

        self.embeddings = self._create_embeddings()
        self.vector_store = self._load_or_create_index()

    def _validate_context(self) -> None:
        if not getattr(self.ctx, "cfg", None):
            raise ValueError("AppContext config is not loaded")

        if not getattr(self.ctx.cfg, "rag", None):
            raise ValueError("RAG config is not registered in AppContext")

    def _create_embeddings(self) -> OllamaEmbeddings:
        """현재는 Ollama Embedding을 기본 구현으로 사용합니다."""
        model = (
            self.config.embedding_model
        )
        base_url = (
            self.config.embedding_base_url
        )

        return OllamaEmbeddings(
            model=model,
            base_url=base_url,
        )

    def search(
        self,
        query: str,
        *,
        k: int = 3,
        include_score: bool = False,
    ) -> list[RetrievedDocument]:
        """유사 문서를 일반화된 RetrievedDocument 목록으로 반환합니다."""
        normalized_query = (query or "").strip()
        if not normalized_query or self.vector_store is None:
            return []

        try:
            if include_score:
                results = self.vector_store.similarity_search_with_score(
                    normalized_query,
                    k=k,
                )
                return [
                    RetrievedDocument(
                        content=document.page_content,
                        metadata=dict(document.metadata or {}),
                        score=float(score),
                    )
                    for document, score in results
                ]

            documents = self.vector_store.similarity_search(
                normalized_query,
                k=k,
            )
            return [
                RetrievedDocument(
                    content=document.page_content,
                    metadata=dict(document.metadata or {}),
                )
                for document in documents
            ]

        except Exception as exc:
            self._log("error", f"[RAG] Search failed: {exc}")
            return []

    async def asearch(
        self,
        query: str,
        *,
        k: int = 3,
        include_score: bool = False,
    ) -> list[RetrievedDocument]:
        return await to_thread(
            self.search,
            query,
            k=k,
            include_score=include_score,
        )

    def search_text(
        self,
        query: str,
        *,
        k: int = 3,
    ) -> str:
        """LLM 프롬프트에 바로 삽입할 수 있는 문자열 컨텍스트를 반환합니다."""
        documents = self.search(query, k=k)
        return self.format_documents(documents)

    async def asearch_text(
        self,
        query: str,
        *,
        k: int = 3,
    ) -> str:
        documents = await self.asearch(query, k=k)
        return self.format_documents(documents)

    @staticmethod
    def format_documents(documents: list[RetrievedDocument]) -> str:
        """검색 결과를 도메인에 종속되지 않은 일반 문서 형식으로 변환합니다."""
        formatted: list[str] = []

        for index, document in enumerate(documents, start=1):
            title = (
                document.metadata.get("title")
                or document.metadata.get("article_title")
                or document.metadata.get("file_name")
                or f"Document {index}"
            )
            formatted.append(f"[{title}]\n{document.content}")

        return "\n\n".join(formatted)

    def rebuild_index(self) -> bool:
        """기존 인덱스를 무시하고 chunks 파일에서 다시 생성합니다."""
        self.vector_store = self._build_index()
        return self.vector_store is not None

    @property
    def is_ready(self) -> bool:
        return self.vector_store is not None

    def _load_or_create_index(self):
        if os.path.exists(self.index_path):
            try:
                vector_store = FAISS.load_local(
                    self.index_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                self._log("info", f"[RAG] Index loaded: {self.index_path}")
                return vector_store
            except Exception as exc:
                self._log(
                    "warning",
                    f"[RAG] Failed to load index: {exc}. Rebuilding...",
                )

        return self._build_index()

    def _build_index(self):
        chunks = self._load_chunks()
        if not chunks:
            return None

        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue

            text = str(chunk.get("text") or "").strip()
            if not text:
                continue

            metadata = {
                key: value
                for key, value in chunk.items()
                if key != "text" and value is not None
            }

            texts.append(text)
            metadatas.append(metadata)

        if not texts:
            self._log("warning", "[RAG] No valid chunk texts found")
            return None

        try:
            vector_store = FAISS.from_texts(
                texts=texts,
                embedding=self.embeddings,
                metadatas=metadatas,
            )
            vector_store.save_local(self.index_path)
            self._log(
                "info",
                f"[RAG] Index built: documents={len(texts)} path={self.index_path}",
            )
            return vector_store
        except Exception as exc:
            self._log("error", f"[RAG] Failed to build index: {exc}")
            return None

    def _load_chunks(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.chunks_path):
            self._log(
                "warning",
                f"[RAG] Chunks file not found: {self.chunks_path}",
            )
            return []

        try:
            with open(self.chunks_path, "rb") as file:
                data = orjson.loads(file.read())
        except Exception as exc:
            self._log("error", f"[RAG] Failed to load chunks: {exc}")
            return []

        if not isinstance(data, list):
            self._log("error", "[RAG] Chunks file must contain a JSON array")
            return []

        return [item for item in data if isinstance(item, dict)]

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)
        if not callable(method):
            return

        try:
            method(message)
        except TypeError:
            method("RAG", message)