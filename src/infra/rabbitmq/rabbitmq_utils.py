# utils/rabbitmq_utils.py
# 'rmq_' prefix

import orjson
import aio_pika
from src.core.responses import ResponseStatus

async def rmq_send_response(ctx, queue_name: str, body: dict):
    """
    지정한 queue_name으로 직접 메시지를 전송합니다.
    default exchange 사용 (routing_key = queue_name).

    :param ctx: AppContext
    :param queue_name: 메시지를 보낼 큐 이름
    :param body: JSON 직렬화 가능한 dict
    """
    log = ctx.log
    rmq_handler = ctx.rmq_handler
    
    try:
        # 채널 보장
        if not rmq_handler.channel or rmq_handler.channel.is_closed:
            log.warning("RMQ", "Channel is closed. Reconnecting...")
            await rmq_handler.connect()

        message = aio_pika.Message(body=orjson.dumps(body))

        channel = rmq_handler.get_channel()
        await channel.declare_queue(queue_name, durable=True)
        await channel.default_exchange.publish(message, routing_key=queue_name)

        log.debug("RMQ", f">> Sent message to queue '{queue_name}': {body}")

    except Exception as e:
        log.error("RMQ", f"- Send Response Failed: '{queue_name}': {e}")

async def rmq_send_error(ctx, queue_name: str, original_msg: dict, status: ResponseStatus = ResponseStatus.SERVER_ERROR):
    """
    에러 메시지를 표준 형식으로 전송합니다.
    original_msg는 요청 메시지를 그대로 반영해도 되고, 일부만 포함해도 됩니다.
    """
    log = ctx.log
    status_info = status.info

    error_response = {
        "status": status_info,
        "data": None,
        "original": original_msg
    }

    log.warning("RMQ", f">> Send Error: '{queue_name}': {status_info['code']}")
    await rmq_send_response(ctx, queue_name, error_response)