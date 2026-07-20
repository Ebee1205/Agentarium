from __future__ import annotations

from typing import TYPE_CHECKING

from src.service.agent.actors.base_actor import BaseAgentActor
from src.service.agent.agent_schema import (
    AgentAction,
    AgentActionType,
    AgentReply,
    AgentState,
)

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
        nearby_ids = [
            key
            for key, item in state.agents.items()
            if key != actor.agent_id and item.location_id == actor.location_id
        ]
        location_ids = list(state.world.locations)

        if phase == 0:
            try:
                current_index = location_ids.index(actor.location_id)
            except ValueError:
                current_index = -1
            target_id = location_ids[(current_index + 1) % len(location_ids)]
            return AgentAction(
                action=AgentActionType.MOVE,
                target_location_id=target_id,
                narration=f"{actor.name}가 주변을 살피며 다음 장소로 발걸음을 옮긴다.",
                emotion="curious",
                reason="다른 장소에서 새로운 사건을 찾고 싶다.",
            )

        if phase == 1:
            return AgentAction(
                action=AgentActionType.OBSERVE,
                narration=f"{actor.name}가 몸을 낮추고 주변의 작은 변화를 살핀다.",
                emotion="focused",
                reason="주변에 달라진 점이 있는지 확인한다.",
            )

        if phase == 2 and nearby_ids:
            target_id = nearby_ids[state.world.tick % len(nearby_ids)]
            return AgentAction(
                action=AgentActionType.TALK,
                target_agent_id=target_id,
                narration=f"{actor.name}가 가까이 있는 상대를 향해 조심스럽게 말을 건다.",
                content=self._dialogue(actor.agent_id, target_id, state.world.tick),
                emotion="interested",
                reason="상대가 알고 있는 정보를 확인한다.",
            )

        if phase == 3:
            resource = "food" if actor.needs.get("hunger", 0) >= 25 else "water"
            return AgentAction(
                action=AgentActionType.USE_RESOURCE,
                resource=resource,
                narration=f"{actor.name}가 남은 자원의 양을 확인한 뒤 필요한 만큼 사용한다.",
                emotion="practical",
                reason="현재 필요를 해결한다.",
            )

        return AgentAction(
            action=AgentActionType.WAIT,
            narration=f"{actor.name}가 제자리에 머물며 다른 개체의 움직임을 지켜본다.",
            emotion="calm",
            reason="다른 개체의 행동을 조금 더 관찰한다.",
        )

    async def reply(
        self,
        *,
        state: "SimulationState",
        speaker: AgentState,
        listener: AgentState,
        dialogue: str,
    ) -> AgentReply:
        del state, dialogue
        return AgentReply(
            narration=f"{listener.name}가 {speaker.name}의 표정을 살핀 뒤 짧게 대답한다.",
            content="확실한 건 아니지만, 나도 조금 더 살펴볼게.",
            emotion="cautious",
            reason="상대의 질문에 반응하면서도 단정하지 않으려 한다.",
        )

    @staticmethod
    def _dialogue(actor_id: str, target_id: str, tick: int) -> str:
        lines = [
            "조금 전 이 근처에서 달라진 점을 보지 못했어?",
            "남은 자원에 대해 네 생각을 듣고 싶어.",
            "다음에는 어디를 살펴보는 게 좋을까?",
            "요즘 이곳의 분위기가 달라진 것 같지 않아?",
        ]
        return lines[(tick + len(actor_id) + len(target_id)) % len(lines)]
