from __future__ import annotations

from collections import defaultdict, deque
from enum import Enum
from typing import Any

from src.service.terrarium.terrarium_schema import (
    TerrariumEvent,
    event_type_value,
    model_to_dict,
)


class EventManager:
    """시뮬레이션 도메인 이벤트를 기록하고 TimelineService로 전달합니다."""

    def __init__(self, ctx: Any, timeline_service: Any) -> None:
        self.ctx = ctx
        self.timeline_service = timeline_service
        config = getattr(ctx.cfg, "terrarium", None)
        self.max_events = int(getattr(config, "max_events", 200) or 200)
        self._events: dict[str, deque[TerrariumEvent]] = defaultdict(
            lambda: deque(maxlen=self.max_events)
        )

    async def emit(
        self,
        *,
        simulation_id: str,
        tick: int,
        event_type: str | Enum,
        summary: str,
        actor_id: str | None = None,
        target_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TerrariumEvent:
        event = TerrariumEvent(
            simulation_id=simulation_id,
            tick=tick,
            type=event_type_value(event_type),
            actor_id=actor_id,
            target_id=target_id,
            summary=summary,
            payload=payload or {},
        )
        self._events[simulation_id].append(event)
        await self.timeline_service.publish(event)
        return event

    def list_events(self, simulation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, self.max_events))
        events = list(self._events.get(simulation_id, []))[-limit:]
        return [model_to_dict(event) for event in events]
