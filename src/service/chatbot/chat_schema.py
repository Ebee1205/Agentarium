# src/chatbot/chat_schema.py

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field


class MessageSender(str, Enum):
    """WebSocket 메시지를 생성한 주체입니다."""

    AUTO = "AUTO"
    USER_A = "USER_A"
    USER_B = "USER_B"


class WsStatusSchema(BaseModel):
    """WebSocket 처리 결과 상태입니다."""

    code: str = Field(min_length=1)
    msg: str = Field(min_length=1)


class WsHeaderSchema(BaseModel):
    """라우팅과 메시지 추적에 사용하는 WebSocket 헤더입니다."""

    type: str = Field(min_length=1)
    timestamp: int = Field(gt=0)
    sid: str | None = Field(default=None, min_length=1)
    mid: str = Field(min_length=1)
    sender: MessageSender


class WsBodySchema(BaseModel):
    """
    클라이언트 요청을 포함한 공통 WebSocket Body입니다.

    요청 메시지는 아직 처리 결과가 없을 수 있으므로 status를 선택값으로 둡니다.
    """

    status: WsStatusSchema | None = None
    data: Any = Field(default_factory=dict)


class WsResponseBodySchema(BaseModel):
    """서버 응답용 Body입니다. 서버 처리 결과이므로 status가 필수입니다."""

    status: WsStatusSchema
    data: Any = Field(default_factory=dict)


class WsMessageSchema(BaseModel):
    """Processor가 수신하고 라우팅하는 공통 WebSocket 메시지입니다."""

    hd: WsHeaderSchema
    bd: WsBodySchema


class WsResponseSchema(BaseModel):
    """서버가 클라이언트로 전송하는 WebSocket 응답입니다."""

    hd: WsHeaderSchema
    bd: WsResponseBodySchema


def _validate_model(model_cls, payload: dict):
    """Pydantic v1/v2에서 모두 동작하도록 모델을 검증합니다."""
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload)
    return model_cls.parse_obj(payload)


def schema_to_dict(model: BaseModel) -> dict:
    """Enum을 포함한 Pydantic 모델을 JSON 전송 가능한 dict로 변환합니다."""
    return jsonable_encoder(model)


def parse_ws_message(payload: dict) -> dict:
    """수신 메시지를 검증하고 표준 dict로 반환합니다."""
    model = _validate_model(WsMessageSchema, payload)
    return schema_to_dict(model)


def parse_ws_response(payload: dict) -> dict:
    """서버 응답 메시지를 검증하고 표준 dict로 반환합니다."""
    model = _validate_model(WsResponseSchema, payload)
    return schema_to_dict(model)