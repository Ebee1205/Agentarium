from __future__ import annotations

from pathlib import Path
from typing import Any

from src.service.terrarium.terrarium_schema import (
    AGENT_ACTION_JSON_SCHEMA,
    AgentAction,
    AgentActionType,
    AgentState,
    SimulationState,
    model_to_dict,
)


class AgentManager:
    """Agent 선택, 행동 결정, 기억 갱신을 담당합니다."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.prompt_path = Path("src/service/terrarium/prompts/agent_action.txt")

    def create_default_agents(self) -> dict[str, AgentState]:
        agents = [
            AgentState(
                agent_id="mori",
                name="모리",
                personality={"curiosity": 90, "sociability": 65, "aggression": 20},
                goal="테라리움 밖으로 나갈 단서를 찾는다.",
                secret="연못 아래에서 희미한 빛을 보았다.",
            ),
            AgentState(
                agent_id="dodo",
                name="도도",
                personality={"curiosity": 35, "sociability": 70, "aggression": 30},
                goal="현재의 질서와 공동 자원을 지킨다.",
                secret="식량 일부를 비상용으로 숨겨 두었다.",
            ),
            AgentState(
                agent_id="ruru",
                name="루루",
                personality={"curiosity": 75, "sociability": 45, "aggression": 10},
                goal="다른 개체들이 감추는 비밀을 수집한다.",
                secret="외부 관찰자의 신호를 가끔 알아들을 수 있다.",
            ),
        ]
        agent_map = {agent.agent_id: agent for agent in agents}
        for agent in agents:
            agent.relationships = {
                other.agent_id: 0
                for other in agents
                if other.agent_id != agent.agent_id
            }
        return agent_map

    def choose_actor(self, state: SimulationState) -> AgentState:
        agent_ids = list(state.agents)
        index = max(0, state.world.tick - 1) % len(agent_ids)
        return state.agents[agent_ids[index]]

    async def decide_action(
        self,
        *,
        state: SimulationState,
        actor: AgentState,
    ) -> AgentAction:
        manager = getattr(self.ctx, "llm_manager", None)
        provider_name = getattr(manager, "provider_name", "mock") if manager else "mock"
        if manager is None or provider_name == "mock":
            return self._mock_action(state, actor)

        prompt = self._load_prompt()
        placeholders = {
            "agent": model_to_dict(actor),
            "world": model_to_dict(state.world),
            "other_agents": [
                model_to_dict(agent)
                for agent in state.agents.values()
                if agent.agent_id != actor.agent_id
            ],
        }
        try:
            result = await manager.generate_json(
                prompt,
                placeholders=placeholders,
                response_schema=AGENT_ACTION_JSON_SCHEMA,
                temperature=0.8,
            )
            if not isinstance(result, dict):
                raise ValueError("Agent action must be a JSON object")
            return self._validate_action(result)
        except Exception as exc:
            self._log("warning", f"[ATM] LLM action fallback: {exc}")
            return self._mock_action(state, actor)

    def remember(self, actor: AgentState, summary: str) -> None:
        actor.memories.append(summary)
        del actor.memories[:-10]

    def _mock_action(self, state: SimulationState, actor: AgentState) -> AgentAction:
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
                content=self._mock_dialogue(actor.agent_id, target_id, state.world.tick),
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
    def _mock_dialogue(actor_id: str, target_id: str, tick: int) -> str:
        lines = [
            "아까 연못 근처에서 뭘 본 거야?",
            "식량이 줄고 있는데 알고 있는 게 있어?",
            "오늘 밤에는 어디에 있을 생각이야?",
            "바깥에서 이상한 소리가 들리지 않았어?",
        ]
        return lines[(tick + len(actor_id) + len(target_id)) % len(lines)]

    def _load_prompt(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return "{{agent}}와 {{world}}를 보고 다음 행동을 JSON으로 결정하세요."

    @staticmethod
    def _validate_action(payload: dict[str, Any]) -> AgentAction:
        if hasattr(AgentAction, "model_validate"):
            return AgentAction.model_validate(payload)
        return AgentAction.parse_obj(payload)

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)
        if not callable(method):
            return
        try:
            method(message)
        except TypeError:
            method("ATM", message)
