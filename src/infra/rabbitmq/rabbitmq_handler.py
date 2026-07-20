# handler/rabbitmq_handler.py

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from aio_pika.exceptions import AMQPConnectionError
from functools import partial
import orjson

from src.messaging.rmq_processor import processor

class RabbitMQHandler:
    def __init__(self, ctx):
        self.ctx = ctx
        self.log = ctx.log
        self.cfg = ctx.cfg.rmq

        self.connection = None
        self.channel = None
        self.exchange = None

    async def connect(self):
        try:
            self.log.debug("RMQ", "- Connecting...")
            self.connection = await aio_pika.connect_robust(
                host=self.cfg.host,
                port=self.cfg.port,
                login=self.cfg.user,
                password=self.cfg.password,
            )

            self.channel = await self.connection.channel()
            self.exchange = self.channel.default_exchange

            self.log.info("RMQ", "== Connected")

        except AMQPConnectionError as e:
            self.log.error("RMQ", f"- Connection error: {str(e)}")
            raise

    async def disconnect(self):
        if self.connection:
            try:
                self.log.debug("RMQ", "- Disconnecting...")
                await self.connection.close()
                self.log.info("RMQ", "-- Disconnected")
            except Exception as e:
                self.log.warning(f"[RMQ]    - Disconnect failed: {str(e)}")

    def get_exchange(self):
        if not self.exchange:
            self.log.error("RMQ", "- Exchange not ready")
            raise RuntimeError("Exchange is not initialized")
        return self.exchange

    def get_channel(self):
        if not self.channel:
            self.log.error("RMQ", "- Channel not ready")
            raise RuntimeError("Channel is not initialized")
        return self.channel

    def get_config(self):
        return self.cfg

    async def consume(self, queue_name: str, processor_func):
        if not self.channel:
            self.log.error("RMQ", "- Channel not connected")
            raise RuntimeError("Channel is not connected")

        queue = await self.channel.declare_queue(queue_name, durable=True)

        async def _wrapped_callback(message: AbstractIncomingMessage):
            async with message.process():
                try:
                    data = orjson.loads(message.body)
                    await processor_func(self.ctx, data)
                    self.log.debug("RMQ", f"- Consumed from '{queue_name}': {data}")
                except Exception as e:
                    self.log.error("RMQ", f"- Consume error ({queue_name}): {str(e)}")

        await queue.consume(_wrapped_callback)
        self.log.info("RMQ", f"== Consuming queue '{queue_name}'")

    async def consume_multi(self):
        if not hasattr(self.cfg, "queues"):
            self.log.error("RMQ", "- No 'queues' defined in config")
            return

        for q in self.cfg.queues:
            queue_name = q.get("name")
            queue_type = q.get("type")

            if not queue_name or not queue_type:
                self.log.warning("RMQ", f"- Invalid queue config: {q}")
                continue

            if queue_type in "sub":
                # 큐별로 식별해서 processor에게 넘겨줌
                processor_func = partial(processor, queue_name=queue_name)
                await self.consume(queue_name, processor_func)
            else:
                self.log.debug("RMQ", f"== Skipping publish queue '{queue_name}' (type={queue_type})")