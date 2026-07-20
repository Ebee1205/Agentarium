from __future__ import annotations

from typing import Any

from src.service.agent.agent_event import AgentEventType
from src.service.agent.agent_schema import AgentAction, AgentActionType, AgentState
from src.service.world.world_clock import WorldClock
from src.service.world.world_config import default_locations, load_world_rules
from src.service.world.world_schema import WorldEventType, WorldState


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
        self._ensure_actor_location(
            world,
            actor,
        )

        if action.action == AgentActionType.MOVE:
            return self._move(
                world,
                actor,
                action,
            )

        if action.action == AgentActionType.TALK:
            return self._talk(
                world,
                agents,
                actor,
                action,
            )

        if action.action == AgentActionType.USE_RESOURCE:
            return self._use_resource(
                world,
                actor,
                action,
            )

        if action.action == AgentActionType.OBSERVE:
            location = world.locations[
                actor.location_id
            ]

            return {
                "event_type": AgentEventType.OBSERVED,
                "summary": (
                    f"{actor.name}가 "
                    f"{location.name} 주변을 "
                    "자세히 관찰했다."
                ),
                "target_id": actor.location_id,
                "payload": {
                    "location_id": actor.location_id,
                    "emotion": action.emotion,
                    "reason": action.reason,
                },
            }

        return self._wait_result(
            actor,
            action,
        )

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
        self._ensure_actor_location(
            world,
            actor,
        )

        previous = actor.location_id
        target = action.target_location_id

        if (
            target not in world.locations
            or target == previous
        ):
            target = self._next_location(
                world,
                previous,
            )

        actor.location_id = target
        world.agent_locations[
            actor.agent_id
        ] = target

        return {
            "event_type": AgentEventType.MOVED,
            "summary": (
                f"{actor.name}가 "
                f"{world.locations[previous].name}에서 "
                f"{world.locations[target].name}"
                "(으)로 이동했다."
            ),
            "target_id": target,
            "payload": {
                "from": previous,
                "to": target,
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
        target = agents.get(
            action.target_agent_id or ""
        )

        if (
            target is None
            or target.agent_id == actor.agent_id
        ):
            return self._wait_result(
                actor,
                action,
                summary=(
                    f"{actor.name}는 대화할 상대를 "
                    "찾지 못했다."
                ),
            )

        self._ensure_actor_location(
            world,
            target,
        )

        if target.location_id != actor.location_id:
            return self._wait_result(
                actor,
                action,
                summary=(
                    f"{actor.name}는 "
                    f"{target.name}에게 말하려 했지만 "
                    "같은 장소에 있지 않았다."
                ),
            )

        actor.relationships[
            target.agent_id
        ] = min(
            100,
            (
                actor.relationships.get(
                    target.agent_id,
                    0,
                )
                + 1
            ),
        )

        target.relationships[
            actor.agent_id
        ] = min(
            100,
            (
                target.relationships.get(
                    actor.agent_id,
                    0,
                )
                + 1
            ),
        )

        actor.needs["loneliness"] = max(
            0,
            actor.needs.get("loneliness", 0) - 8,
        )
        target.needs["loneliness"] = max(
            0,
            target.needs.get("loneliness", 0) - 4,
        )

        content = (
            action.content
            or "오늘은 무슨 일이 있었어?"
        )

        return {
            "event_type": AgentEventType.TALKED,
            "summary": (
                f"{actor.name}가 "
                f"{target.name}에게 말했다. "
                f"“{content}”"
            ),
            "target_id": target.agent_id,
            "payload": {
                "content": content,
                "emotion": action.emotion,
                "relationship": actor.relationships[
                    target.agent_id
                ],
                "reason": action.reason,
            },
        }

    def _use_resource(
        self,
        world: WorldState,
        actor: AgentState,
        action: AgentAction,
    ) -> dict[str, Any]:
        resource = (
            action.resource
            if action.resource in world.resources
            else "food"
        )
        remaining = world.resources.get(
            resource,
            0,
        )

        if remaining <= 0:
            return {
                "event_type": AgentEventType.WAITED,
                "summary": (
                    f"{actor.name}는 {resource}을(를) "
                    "찾았지만 남아 있지 않았다."
                ),
                "payload": {
                    "resource": resource,
                    "reason": action.reason,
                },
            }

        world.resources[resource] = remaining - 1

        if resource == "food":
            actor.needs["hunger"] = max(
                0,
                actor.needs.get("hunger", 0) - 20,
            )
        elif resource == "water":
            actor.needs["energy"] = min(
                100,
                actor.needs.get("energy", 0) + 10,
            )

        return {
            "event_type": (
                WorldEventType.RESOURCE_CHANGED
            ),
            "summary": (
                f"{actor.name}가 공동 "
                f"{resource}을(를) 1 사용했다."
            ),
            "target_id": resource,
            "payload": {
                "resource": resource,
                "delta": -1,
                "value": world.resources[resource],
                "reason": action.reason,
            },
        }

    def _ensure_actor_location(
        self,
        world: WorldState,
        actor: AgentState,
    ) -> None:
        if actor.location_id in world.locations:
            world.agent_locations[
                actor.agent_id
            ] = actor.location_id
            return

        if not world.locations:
            raise ValueError(
                "월드에 등록된 Location이 없습니다."
            )

        fallback = (
            "home"
            if "home" in world.locations
            else next(iter(world.locations))
        )

        self._log(
            "warning",
            (
                "[ATM] actor location repaired: "
                f"agent_id={actor.agent_id}, "
                f"location_id={actor.location_id}, "
                f"fallback={fallback}"
            ),
        )

        actor.location_id = fallback
        world.agent_locations[
            actor.agent_id
        ] = fallback

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
    def _wait_result(
        actor: AgentState,
        action: AgentAction,
        *,
        summary: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event_type": AgentEventType.WAITED,
            "summary": (
                summary
                or (
                    f"{actor.name}는 잠시 아무 행동도 "
                    "하지 않고 주변을 지켜봤다."
                )
            ),
            "payload": {
                "emotion": action.emotion,
                "reason": action.reason,
            },
        }

    def _log(
        self,
        level: str,
        message: str,
    ) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)

        if not callable(method):
            return

        try:
            method(message)
        except TypeError:
            method("ATM", message)
