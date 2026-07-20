from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from src.common.ws_responses import (
    MessageSender,
    build_ws_success_response,
)
from src.service.terrarium.terrarium_schema import TerrariumEvent, model_to_dict
from src.service.timeline.timeline_schema import TimelineCategory, TimelineItem


class TimelineService:
    """도메인 이벤트를 화면 표시용 타임라인 항목으로 변환하고 전송합니다."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        config = getattr(ctx.cfg, "terrarium", None)
        self.max_items = int(getattr(config, "max_events", 200) or 200)
        self._items: dict[str, deque[TimelineItem]] = defaultdict(
            lambda: deque(maxlen=self.max_items)
        )

    async def publish(self, event: TerrariumEvent) -> TimelineItem:
        item = self._to_timeline_item(event)
        self._items[event.simulation_id].append(item)

        handler = getattr(self.ctx, "ws_handler", None)
        if handler is not None:
            message = build_ws_success_response(
                event_type="TIMELINE_EVENT",
                sid=event.simulation_id,
                sender=MessageSender.AUTO,
                data={
                    "event": model_to_dict(event),
                    "timeline": model_to_dict(item),
                },
            )
            await handler.broadcast_to_session(event.simulation_id, message)
        return item

    def list_items(self, simulation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, self.max_items))
        items = list(self._items.get(simulation_id, []))[-limit:]
        return [model_to_dict(item) for item in items]

    def _to_timeline_item(self, event: TerrariumEvent) -> TimelineItem:
        category, title, importance = self._classify(event.type)
        return TimelineItem(
            simulation_id=event.simulation_id,
            tick=event.tick,
            category=category,
            source_event_type=event.type,
            title=title,
            summary=event.summary,
            importance=importance,
            actor_id=event.actor_id,
            target_id=event.target_id,
            data=event.payload,
            created_at=event.created_at,
        )

    @staticmethod
    def _classify(event_type: str) -> tuple[TimelineCategory, str, int]:
        if event_type == "RELATIONSHIP_CHANGED":
            return TimelineCategory.RELATIONSHIP, "관계 변화", 3
        if event_type == "RESOURCE_CHANGED":
            return TimelineCategory.RESOURCE, "자원 변화", 2
        if event_type.startswith("AGENT_") or event_type == "EMOTION_CHANGED":
            return TimelineCategory.AGENT, "Agent 행동", 2
        if event_type in {"WORLD_EVENT", "NEED_CHANGED"}:
            return TimelineCategory.WORLD, "월드 변화", 2
        if event_type == "TICK_STARTED":
            return TimelineCategory.SYSTEM, "시간 경과", 1
        return TimelineCategory.SYSTEM, "시뮬레이션", 3
