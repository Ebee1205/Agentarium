# utils/websocket_utils.py
# 'ws_' prefix


async def ws_send_response(ctx, sid: str, body: dict) -> bool:
    """
    현재 sid에 연결된 모든 WebSocket 클라이언트로 응답을 전송합니다.

    연결이 없거나 모든 전송이 실패하면 False를 반환합니다.

    :param ctx: AppContext
    :param sid: 세션 ID
    :param body: 전송할 JSON 직렬화 가능한 dict
    """
    sent_count = await ctx.ws_handler.broadcast_to_session(sid, body)

    if sent_count == 0:
        ctx.log.warning("WS", f"- Message not sent: no active connection for sid={sid}")
        return False

    ctx.log.info(
        "WS",
        f">> Sent message: sid={sid}, connections={sent_count}, body={body}",
    )
    return True