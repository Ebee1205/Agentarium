from __future__ import annotations

from typing import Any

from src.service.agent.agent_event import AgentEventType
from src.service.agent.agent_schema import (
    AgentAction,
    AgentActionType,
    AgentState,
)
from src.service.world.world_clock import WorldClock
from src.service.world.world_config import (
    default_locations,
    load_world_rules,
)
from src.service.world.world_schema import (
    WorldEventType,
    WorldState,
)


class WorldManager:
    """월드 상태, 시간, 자원 및 Agent 행동 결과를 계산합니다."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.rules = load_world_rules(ctx)
        self.clock = WorldClock(self.rules)

    def create_world(
        self,
        agents: dict[str, AgentState],
    ) -> WorldState:
        locations = default_locations()

        if not locations:
            raise ValueError(
                "월드에 등록된 Location이 없습니다."
            )

        default_location_id = (
            "home"
            if "home" in locations
            else next(iter(locations))
        )

        agent_locations: dict[str, str] = {}

        for agent_id, agent in agents.items():
            if agent.location_id not in locations:
                self._log(
                    "warning",
                    (
                        "[ATM] invalid location corrected: "
                        f"agent_id={agent_id}, "
                        f"location_id={agent.location_id}, "
                        f"default={default_location_id}"
                    ),
                )
                agent.location_id = default_location_id

            agent_locations[agent_id] = (
                agent.location_id
            )

        return WorldState(
            hour=self.rules.day_start_hour,
            resources={
                "food": self.rules.initial_food,
                "water": self.rules.initial_water,
            },
            locations=locations,
            agent_locations=agent_locations,
        )

    def advance(
        self,
        world: WorldState,
    ) -> list[dict[str, Any]]:
        self.clock.advance(world)
        changes: list[dict[str, Any]] = []

        if (
            world.tick % 3 == 0
            and world.resources.get("food", 0) > 0
        ):
            world.resources["food"] -= 1
            changes.append(
                {
                    "event_type": (
                        WorldEventType.RESOURCE_CHANGED
                    ),
                    "summary": (
                        "테라리움의 공동 식량이 1 감소했다."
                    ),
                    "payload": {
                        "resource": "food",
                        "delta": -1,
                        "value": world.resources["food"],
                    },
                }
            )

        if world.tick % 4 == 0:
            world.weather = (
                "rain"
                if world.weather == "clear"
                else "clear"
            )

            changes.append(
                {
                    "event_type": (
                        WorldEventType.WORLD_EVENT
                    ),
                    "summary": (
                        "테라리움에 비가 내리기 시작했다."
                        if world.weather == "rain"
                        else "비가 그치고 조명이 밝아졌다."
                    ),
                    "payload": {
                        "weather": world.weather
                    },
                }
            )

        return changes

    def resolve_action(
        self,
        *,
        world: WorldState,
        agents: dict[str, AgentState],
        actor: AgentState,
        action: AgentAction,
    ) -> dict[str, Any]:
        # event type 분기는 상태 변경을 위한 것이다.
        # 화면에 보일 문장 자체는 action.narration/content에서 가져온다.
        if action.action == AgentActionType.MOVE:
            return self._move(world, actor, action)
        if action.action == AgentActionType.TALK:
            return self._talk(world, agents, actor, action)
        if action.action == AgentActionType.USE_RESOURCE:
            return self._use_resource(world, actor, action)
        if action.action == AgentActionType.OBSERVE:
            location_name = world.locations[actor.location_id].name
            fallback = f"{actor.name}가 {location_name} 주변을 자세히 관찰했다."
            return {
                "event_type": AgentEventType.OBSERVED,
                "summary": self._summary(action, fallback),
                "target_id": actor.location_id,
                "payload": {
                    "location_id": actor.location_id,
                    "narration": action.narration,
                    "emotion": action.emotion,
                    "reason": action.reason,
                },
            }
        return self._wait_result(actor, action)

    def apply_passive_needs(
        self,
        agents: dict[str, AgentState],
        time_of_day: str,
    ) -> None:
        energy_cost = (
            self.rules.energy_night_cost
            if time_of_day == "NIGHT"
            else self.rules.energy_day_cost
        )

        for agent in agents.values():
            agent.needs["hunger"] = min(
                100,
                (
                    agent.needs.get("hunger", 0)
                    + self.rules.hunger_per_tick
                ),
            )
            agent.needs["energy"] = max(
                0,
                (
                    agent.needs.get("energy", 0)
                    - energy_cost
                ),
            )
            agent.needs["loneliness"] = min(
                100,
                agent.needs.get("loneliness", 0) + 1,
            )

    def _move(
        self,
        world: WorldState,
        actor: AgentState,
        action: AgentAction,
    ) -> dict[str, Any]:
        target = action.target_location_id
        if target not in world.locations:
            target = self._next_location(world, actor.location_id)

        previous = actor.location_id
        actor.location_id = target
        world.agent_locations[actor.agent_id] = target
        fallback = (
            f"{actor.name}가 {world.locations[previous].name}에서 "
            f"{world.locations[target].name}(으)로 이동했다."
        )
        return {
            "event_type": AgentEventType.MOVED,
            "summary": self._summary(action, fallback),
            "target_id": target,
            "payload": {
                "from": previous,
                "to": target,
                "narration": action.narration,
                "emotion": action.emotion,
                "reason": action.reason,
            },
        }

    def _talk(
        self,
        world: WorldState,
        agents: dict[str, AgentState],
        actor: AgentState,
        action: AgentAction,
    ) -> dict[str, Any]:
        target = agents.get(action.target_agent_id or "")
        if target is None or target.agent_id == actor.agent_id:
            return self._wait_result(actor, action)
        if target.location_id != actor.location_id:
            return self._wait_result(actor, action)
        if not action.content or not action.content.strip():
            return self._wait_result(actor, action)

        relationship_delta = 2 if action.reply_content else 1
        actor.relationships[target.agent_id] = min(
            100,
            actor.relationships.get(target.agent_id, 0) + relationship_delta,
        )
        target.relationships[actor.agent_id] = min(
            100,
            target.relationships.get(actor.agent_id, 0) + relationship_delta,
        )
        actor.needs["loneliness"] = max(
            0,
            actor.needs.get("loneliness", 0) - 8,
        )
        target.needs["loneliness"] = max(
            0,
            target.needs.get("loneliness", 0) - 5,
        )
        if action.reply_emotion:
            target.current_emotion = action.reply_emotion

        summary_lines: list[str] = []
        if action.narration.strip():
            summary_lines.append(action.narration.strip())
        summary_lines.append(f"{actor.name}: “{action.content.strip()}”")
        if action.reply_narration and action.reply_narration.strip():
            summary_lines.append(action.reply_narration.strip())
        if action.reply_content and action.reply_content.strip():
            summary_lines.append(f"{target.name}: “{action.reply_content.strip()}”")

        dialogue = [
            {
                "agent_id": actor.agent_id,
                "name": actor.name,
                "content": action.content.strip(),
                "emotion": action.emotion,
                "source": action.source,
            }
        ]
        if action.reply_content and action.reply_content.strip():
            dialogue.append(
                {
                    "agent_id": target.agent_id,
                    "name": target.name,
                    "content": action.reply_content.strip(),
                    "emotion": action.reply_emotion,
                    "source": action.reply_source,
                }
            )

        return {
            "event_type": AgentEventType.TALKED,
            "summary": "\n".join(summary_lines),
            "target_id": target.agent_id,
            "payload": {
                "location_id": world.agent_locations.get(actor.agent_id),
                "narration": action.narration,
                "dialogue": dialogue,
                # 기존 클라이언트 호환용
                "content": action.content,
                "reply_content": action.reply_content,
                "emotion": action.emotion,
                "reply_emotion": action.reply_emotion,
                "relationship": actor.relationships[target.agent_id],
                "reason": action.reason,
                "reply_reason": action.reply_reason,
            },
        }

    def _use_resource(
        self,
        world: WorldState,
        actor: AgentState,
        action: AgentAction,
    ) -> dict[str, Any]:
        resource = action.resource if action.resource in world.resources else "food"
        remaining = world.resources.get(resource, 0)
        if remaining <= 0:
            fallback = f"{actor.name}는 {resource}을(를) 찾았지만 남아 있지 않았다."
            return {
                "event_type": AgentEventType.WAITED,
                "summary": self._summary(action, fallback),
                "payload": {
                    "resource": resource,
                    "narration": action.narration,
                    "reason": action.reason,
                },
            }

        world.resources[resource] = remaining - 1
        if resource == "food":
            actor.needs["hunger"] = max(0, actor.needs.get("hunger", 0) - 20)
        elif resource == "water":
            actor.needs["energy"] = min(100, actor.needs.get("energy", 0) + 10)

        fallback = f"{actor.name}가 공동 {resource}을(를) 1 사용했다."
        return {
            "event_type": WorldEventType.RESOURCE_CHANGED,
            "summary": self._summary(action, fallback),
            "target_id": resource,
            "payload": {
                "resource": resource,
                "delta": -1,
                "value": world.resources[resource],
                "narration": action.narration,
                "emotion": action.emotion,
                "reason": action.reason,
            },
        }

    @staticmethod
    def _next_location(
        world: WorldState,
        current: str,
    ) -> str:
        location_ids = list(world.locations)

        if not location_ids:
            raise ValueError(
                "월드에 등록된 Location이 없습니다."
            )

        try:
            index = location_ids.index(current)
        except ValueError:
            return location_ids[0]

        return location_ids[
            (index + 1) % len(location_ids)
        ]

    @staticmethod
    def _summary(action: AgentAction, fallback: str) -> str:
        narration = action.narration.strip()
        return narration or fallback

    @classmethod
    def _wait_result(
        cls,
        actor: AgentState,
        action: AgentAction,
    ) -> dict[str, Any]:
        fallback = f"{actor.name}는 잠시 아무 행동도 하지 않고 주변을 지켜봤다."
        return {
            "event_type": AgentEventType.WAITED,
            "summary": cls._summary(action, fallback),
            "payload": {
                "narration": action.narration,
                "emotion": action.emotion,
                "reason": action.reason,
            },
        }
