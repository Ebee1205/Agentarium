from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.service.agent.actors.llm_actor import LLMAgentActor
from src.service.agent.actors.mock_actor import MockAgentActor
from src.service.agent.agent_schema import AgentAction, AgentState

if TYPE_CHECKING:
    from src.service.terrarium.terrarium_schema import SimulationState


class AgentManager:
    """Agent 생성, 선택, 행동 결정 및 기억 갱신 담당."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        config = getattr(ctx.cfg, "terrarium", None)
        prompt_path = str(
            getattr(config, "prompt_path", "src/service/prompts/agent_action.txt")
        )
        self.max_memories = int(getattr(config, "max_memories", 10) or 10)
        self.use_llm = bool(getattr(config, "use_llm", False))
        self.mock_actor = MockAgentActor(ctx)
        self.llm_actor = LLMAgentActor(ctx, prompt_path=prompt_path)

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

    def choose_actor(self, state: "SimulationState") -> AgentState:
        if not state.agents:
            raise RuntimeError("Simulation has no agents")
        agent_ids = list(state.agents)
        index = max(0, state.world.tick - 1) % len(agent_ids)
        return state.agents[agent_ids[index]]

    async def decide_action(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
    ) -> AgentAction:
        if not self.use_llm:
            return await self.mock_actor.decide(state=state, actor=actor)

        try:
            return await self.llm_actor.decide(state=state, actor=actor)
        except Exception as exc:
            self._log("warning", f"[ATM] LLM action fallback: {exc}")
            return await self.mock_actor.decide(state=state, actor=actor)

    def remember(self, actor: AgentState, summary: str) -> None:
        actor.memories.append(summary)
        if len(actor.memories) > self.max_memories:
            del actor.memories[:-self.max_memories]

    def set_emotion(self, actor: AgentState, emotion: str) -> None:
        if emotion:
            actor.current_emotion = emotion

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)
        if not callable(method):
            return
        try:
            method(message)
        except TypeError:
            method("ATM", message)
