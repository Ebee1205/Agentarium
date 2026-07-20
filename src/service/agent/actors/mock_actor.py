from __future__ import annotations

from typing import TYPE_CHECKING

from src.service.agent.actors.base_actor import BaseAgentActor
from src.service.agent.agent_schema import AgentAction, AgentActionType, AgentState

if TYPE_CHECKING:
    from src.service.terrarium.terrarium_schema import SimulationState


class MockAgentActor(BaseAgentActor):
    """네트워크 호출 없이 반복 가능한 행동을 만드는 테스트 Actor."""

    async def decide(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
    ) -> AgentAction:
        phase = state.world.tick % 5
        other_ids = [key for key in state.agents if key != actor.agent_id]
        location_ids = list(state.world.locations)

        if phase == 0:
            try:
                current_index = location_ids.index(actor.location_id)
            except ValueError:
                current_index = -1
            return AgentAction(
                action=AgentActionType.MOVE,
                target_location_id=location_ids[(current_index + 1) % len(location_ids)],
                emotion="curious",
                reason="다른 장소에서 새로운 사건을 찾고 싶다.",
            )

        if phase == 1:
            return AgentAction(
                action=AgentActionType.OBSERVE,
                emotion="focused",
                reason="주변에 달라진 점이 있는지 확인한다.",
            )

        if phase == 2 and other_ids:
            target_id = other_ids[state.world.tick % len(other_ids)]
            return AgentAction(
                action=AgentActionType.TALK,
                target_agent_id=target_id,
                content=self._dialogue(actor.agent_id, target_id, state.world.tick),
                emotion="interested",
                reason="상대가 알고 있는 정보를 확인한다.",
            )

        if phase == 3:
            resource = "food" if actor.needs.get("hunger", 0) >= 25 else "water"
            return AgentAction(
                action=AgentActionType.USE_RESOURCE,
                resource=resource,
                emotion="practical",
                reason="현재 필요를 해결한다.",
            )

        return AgentAction(
            action=AgentActionType.WAIT,
            emotion="calm",
            reason="다른 개체의 행동을 조금 더 관찰한다.",
        )

    @staticmethod
    def _dialogue(actor_id: str, target_id: str, tick: int) -> str:
        lines = [
            "아까 연못 근처에서 뭘 본 거야?",
            "식량이 줄고 있는데 알고 있는 게 있어?",
            "오늘 밤에는 어디에 있을 생각이야?",
            "바깥에서 이상한 소리가 들리지 않았어?",
        ]
        return lines[(tick + len(actor_id) + len(target_id)) % len(lines)]
