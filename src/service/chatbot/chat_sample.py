# src/service/chatbot/chat_sample.py

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, WebSocket

from src.service.chatbot.chat_responses import (
    MessageSender,
    build_ws_error_response,
    build_ws_success_response,
)
from src.common.responses import ResponseStatus


router = APIRouter(
    prefix="/ws",
    tags=["websocket"],
)


async def sample_chat_processor(ctx, websocket: WebSocket, message: dict) -> dict:
    """
    WebSocketHandler.process()에서 호출하는 샘플 Processor입니다.

    hd.type을 기준으로 이벤트를 라우팅하고, 반드시 hd/bd WebSocket 응답
    스키마를 반환합니다. 직접 전송할 경우에는 None을 반환해도 됩니다.
    """
    header = message["hd"]
    body = message["bd"]

    event_type = header["type"]
    sid = header["sid"]
    sender = header["sender"]
    data: Any = body.get("data", {})

    if event_type == "PING":
        return build_ws_success_response(
            event_type="PONG",
            sid=sid,
            sender=MessageSender.AUTO,
            data={
                "request_mid": header["mid"],
            },
        )

    if event_type == "CHAT_MESSAGE":
        content = data.get("content") if isinstance(data, dict) else None

        if not isinstance(content, str) or not content.strip():
            return build_ws_error_response(
                event_type="CHAT_ERROR",
                sid=sid,
                sender=MessageSender.AUTO,
                status=ResponseStatus.BAD_REQUEST,
                data={
                    "reason": "메시지 내용이 누락되었습니다.",
                    "field": "bd.data.content",
                    "request_mid": header["mid"],
                },
            )

        return build_ws_success_response(
            event_type="CHAT_RESPONSE",
            sid=sid,
            sender=MessageSender.AUTO,
            data={
                "content": f"[{sender}] {content}",
                "request_mid": header["mid"],
            },
        )

    return build_ws_error_response(
        event_type="WS_ERROR",
        sid=sid,
        sender=MessageSender.AUTO,
        status=ResponseStatus.BAD_REQUEST,
        data={
            "reason": f"지원하지 않는 이벤트 타입입니다: {event_type}",
            "request_mid": header["mid"],
        },
    )


@router.websocket("/chat/{sid}")
async def chatbot_websocket(websocket: WebSocket, sid: str) -> None:
    """
    샘플 접속 주소: ws://localhost:8000/ws/chat/{sid}

    AppContext는 FastAPI의 app.state.ctx에 등록되어 있다고 가정합니다.
    연결 라이프사이클은 WebSocketHandler의 init -> process -> destroy를
    그대로 따릅니다.
    """
    ctx = getattr(websocket.app.state, "ctx", None)
    if ctx is None:
        # accept 이전에는 WebSocketHandler를 사용할 수 없으므로 직접 종료합니다.
        await websocket.close(code=1011, reason="AppContext is not initialized")
        return

    handler = ctx.ws_handler

    try:
        connection_id = await handler.init(websocket, sid=sid)

        connected_response = build_ws_success_response(
            event_type="SESSION_CONNECTED",
            sid=sid,
            sender=MessageSender.AUTO,
            data={
                "connection_id": connection_id,
                "message": "WebSocket 연결이 완료되었습니다.",
            },
        )

        # 같은 sid의 다른 클라이언트가 아니라, 방금 연결된 클라이언트에만 전송합니다.
        sent = await handler.send_to_connection(websocket, connected_response)
        if not sent:
            return

        await handler.process(websocket, sample_chat_processor)

    except Exception as exc:
        ctx.log.error("WS", f"- WebSocket router error: sid={sid}, error={exc}")
        await handler.destroy(websocket, close=True, code=1011)


def register_websocket_router(app: FastAPI) -> None:
    """FastAPI 애플리케이션에 샘플 WebSocket 라우터를 등록합니다."""
    app.include_router(router)