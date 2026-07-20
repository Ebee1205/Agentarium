from __future__ import annotations

from typing import Any

from src.service.terrarium.terrarium_schema import (
    AgentAction,
    AgentActionType,
    AgentState,
    LocationState,
    TerrariumEventType,
    WorldState,
)


class WorldManager:
    LOCATIONS = {
        "nest": LocationState(
            location_id="nest",
            name="둥지",
            description="개체들이 쉬거나 대화하는 안전한 장소",
        ),
        "pond": LocationState(
            location_id="pond",
            name="연못",
            description="물을 구하거나 수상한 흔적을 발견할 수 있는 장소",
        ),
        "storage": LocationState(
            location_id="storage",
            name="식량 보관소",
            description="공동 식량이 쌓여 있는 장소",
        ),
    }

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def create_world(self, agents: dict[str, AgentState]) -> WorldState:
        return WorldState(
            locations={key: value for key, value in self.LOCATIONS.items()},
            agent_locations={
                agent_id: agent.location_id for agent_id, agent in agents.items()
            },
        )

    def advance(self, world: WorldState) -> list[dict[str, Any]]:
        world.tick += 1
        cycle = world.tick % 16
        world.time_of_day = "NIGHT" if cycle >= 12 else "DAY"

        changes: list[dict[str, Any]] = []
        if world.tick % 3 == 0 and world.resources.get("food", 0) > 0:
            world.resources["food"] -= 1
            changes.append(
                {
                    "event_type": TerrariumEventType.RESOURCE_CHANGED,
                    "summary": "테라리움의 공동 식량이 1 감소했다.",
                    "payload": {
                        "resource": "food",
                        "delta": -1,
                        "value": world.resources["food"],
                    },
                }
            )

        if world.tick % 4 == 0:
            world.weather = "rain" if world.weather == "clear" else "clear"
            changes.append(
                {
                    "event_type": TerrariumEventType.WORLD_EVENT,
                    "summary": (
                        "테라리움에 비가 내리기 시작했다."
                        if world.weather == "rain"
                        else "비가 그치고 조명이 밝아졌다."
                    ),
                    "payload": {"weather": world.weather},
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
        if action.action == AgentActionType.MOVE:
            target = action.target_location_id
            if target not in world.locations:
                target = self._next_location(actor.location_id)
            previous = actor.location_id
            actor.location_id = target
            world.agent_locations[actor.agent_id] = target
            return {
                "event_type": TerrariumEventType.AGENT_MOVED,
                "summary": (
                    f"{actor.name}가 {world.locations[previous].name}에서 "
                    f"{world.locations[target].name}(으)로 이동했다."
                ),
                "target_id": target,
                "payload": {
                    "from": previous,
                    "to": target,
                    "reason": action.reason,
                },
            }

        if action.action == AgentActionType.TALK:
            target = agents.get(action.target_agent_id or "")
            if target is None or target.agent_id == actor.agent_id:
                target = next(
                    (item for item in agents.values() if item.agent_id != actor.agent_id),
                    None,
                )
            if target is None:
                return self._wait_result(actor, action)

            previous = actor.relationships.get(target.agent_id, 0)
            actor.relationships[target.agent_id] = min(100, previous + 1)
            target.relationships[actor.agent_id] = min(
                100, target.relationships.get(actor.agent_id, 0) + 1
            )
            content = action.content or "오늘은 무슨 일이 있었어?"
            return {
                "event_type": TerrariumEventType.AGENT_TALKED,
                "summary": f"{actor.name}가 {target.name}에게 말했다. “{content}”",
                "target_id": target.agent_id,
                "payload": {
                    "content": content,
                    "emotion": action.emotion,
                    "relationship": actor.relationships[target.agent_id],
                    "reason": action.reason,
                },
            }

        if action.action == AgentActionType.USE_RESOURCE:
            resource = action.resource if action.resource in world.resources else "food"
            remaining = world.resources.get(resource, 0)
            if remaining <= 0:
                return {
                    "event_type": TerrariumEventType.AGENT_WAITED,
                    "summary": f"{actor.name}는 {resource}을(를) 찾았지만 남아 있지 않았다.",
                    "payload": {"resource": resource, "reason": action.reason},
                }
            world.resources[resource] = remaining - 1
            if resource == "food":
                actor.needs["hunger"] = max(0, actor.needs.get("hunger", 0) - 20)
            elif resource == "water":
                actor.needs["energy"] = min(100, actor.needs.get("energy", 0) + 10)
            return {
                "event_type": TerrariumEventType.RESOURCE_CHANGED,
                "summary": f"{actor.name}가 공동 {resource}을(를) 1 사용했다.",
                "target_id": resource,
                "payload": {
                    "resource": resource,
                    "delta": -1,
                    "value": world.resources[resource],
                    "reason": action.reason,
                },
            }

        if action.action == AgentActionType.OBSERVE:
            location_name = world.locations[actor.location_id].name
            return {
                "event_type": TerrariumEventType.AGENT_OBSERVED,
                "summary": f"{actor.name}가 {location_name} 주변을 자세히 관찰했다.",
                "target_id": actor.location_id,
                "payload": {
                    "location_id": actor.location_id,
                    "emotion": action.emotion,
                    "reason": action.reason,
                },
            }

        return self._wait_result(actor, action)

    @staticmethod
    def apply_passive_needs(agents: dict[str, AgentState], time_of_day: str) -> None:
        for agent in agents.values():
            agent.needs["hunger"] = min(100, agent.needs.get("hunger", 0) + 2)
            agent.needs["energy"] = max(
                0,
                agent.needs.get("energy", 0) - (2 if time_of_day == "NIGHT" else 1),
            )
            agent.needs["loneliness"] = min(
                100, agent.needs.get("loneliness", 0) + 1
            )

    def _next_location(self, current: str) -> str:
        location_ids = list(self.LOCATIONS)
        try:
            index = location_ids.index(current)
        except ValueError:
            return location_ids[0]
        return location_ids[(index + 1) % len(location_ids)]

    @staticmethod
    def _wait_result(actor: AgentState, action: AgentAction) -> dict[str, Any]:
        return {
            "event_type": TerrariumEventType.AGENT_WAITED,
            "summary": f"{actor.name}는 잠시 아무 행동도 하지 않고 주변을 지켜봤다.",
            "payload": {"emotion": action.emotion, "reason": action.reason},
        }
