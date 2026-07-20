# src/service/chatbot/chat_responses.py

from __future__ import annotations

import time
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from src.common.responses import ResponseStatus
from src.service.chatbot.chat_schema import (
    MessageSender,
    WsHeaderSchema,
    WsResponseBodySchema,
    WsResponseSchema,
    WsStatusSchema,
    schema_to_dict,
)


def current_timestamp_ms() -> int:
    """현재 시각을 Unix timestamp 밀리초 단위로 반환합니다."""
    return time.time_ns() // 1_000_000


def generate_message_id() -> str:
    """WebSocket 메시지 고유 ID를 생성합니다."""
    return f"msg_{uuid4().hex}"


def _event_type_value(event_type: str | Enum) -> str:
    value = event_type.value if isinstance(event_type, Enum) else event_type
    if not isinstance(value, str) or not value.strip():
        raise ValueError("event_type must be a non-empty string")
    return value


def _build_ws_status(status: ResponseStatus) -> WsStatusSchema:
    """REST 상태 정의에서 WebSocket에 필요한 code와 msg만 추출합니다."""
    return WsStatusSchema(
        code=status.info["code"],
        msg=status.info["msg"],
    )


def build_ws_response(
    *,
    event_type: str | Enum,
    sid: str | None,
    sender: MessageSender,
    status: ResponseStatus,
    data: Any = None,
    mid: str | None = None,
    timestamp: int | None = None,
) -> dict:
    """
    hd/bd 규격의 WebSocket 응답을 생성합니다.

    hd.type은 Processor 및 클라이언트에서 사용하는 이벤트 라우팅 타입입니다.
    hd.mid는 메시지 자체의 식별자이며 timestamp와 별도로 관리합니다.
    """
    response = WsResponseSchema(
        hd=WsHeaderSchema(
            type=_event_type_value(event_type),
            timestamp=timestamp or current_timestamp_ms(),
            sid=sid,
            mid=mid or generate_message_id(),
            sender=sender,
        ),
        bd=WsResponseBodySchema(
            status=_build_ws_status(status),
            data=jsonable_encoder(data) if data is not None else {},
        ),
    )
    return schema_to_dict(response)


def build_ws_success_response(
    *,
    event_type: str | Enum,
    sid: str | None,
    sender: MessageSender = MessageSender.AUTO,
    data: Any = None,
    mid: str | None = None,
    timestamp: int | None = None,
) -> dict:
    """WebSocket 성공 응답을 생성합니다."""
    return build_ws_response(
        event_type=event_type,
        sid=sid,
        sender=sender,
        status=ResponseStatus.SUCCESS,
        data=data,
        mid=mid,
        timestamp=timestamp,
    )


def build_ws_error_response(
    *,
    event_type: str | Enum,
    sid: str | None,
    status: ResponseStatus = ResponseStatus.BAD_REQUEST,
    sender: MessageSender = MessageSender.AUTO,
    data: Any = None,
    mid: str | None = None,
    timestamp: int | None = None,
) -> dict:
    """WebSocket 오류 응답을 생성합니다."""
    if status.http_code < 400:
        status = ResponseStatus.SERVER_ERROR

    return build_ws_response(
        event_type=event_type,
        sid=sid,
        sender=sender,
        status=status,
        data=data,
        mid=mid,
        timestamp=timestamp,
    )