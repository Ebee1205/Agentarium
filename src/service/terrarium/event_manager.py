from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from src.service.chatbot.chat_responses import (
    MessageSender,
    build_ws_success_response,
)
from src.service.terrarium.terrarium_schema import (
    TerrariumEvent,
    TerrariumEventType,
    model_to_dict,
)


class EventManager:
    """시뮬레이션 이벤트 기록과 WebSocket 타임라인 발행을 담당합니다."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        terrarium_cfg = getattr(ctx.cfg, "terrarium", None)
        self.max_events = int(getattr(terrarium_cfg, "max_events", 200) or 200)
        self._events: dict[str, deque[TerrariumEvent]] = defaultdict(
            lambda: deque(maxlen=self.max_events)
        )

    async def emit(
        self,
        *,
        simulation_id: str,
        tick: int,
        event_type: TerrariumEventType,
        summary: str,
        actor_id: str | None = None,
        target_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TerrariumEvent:
        event = TerrariumEvent(
            simulation_id=simulation_id,
            tick=tick,
            type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            summary=summary,
            payload=payload or {},
        )
        self._events[simulation_id].append(event)
        await self._publish(event)
        return event

    def list_events(self, simulation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, self.max_events))
        events = list(self._events.get(simulation_id, []))[-limit:]
        return [model_to_dict(event) for event in events]

    async def _publish(self, event: TerrariumEvent) -> None:
        handler = getattr(self.ctx, "ws_handler", None)
        if handler is None:
            return

        message = build_ws_success_response(
            event_type="TIMELINE_EVENT",
            sid=event.simulation_id,
            sender=MessageSender.AUTO,
            data={"event": model_to_dict(event)},
        )
        await handler.broadcast_to_session(event.simulation_id, message)
