from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.service.agent.actors.llm_actor import LLMAgentActor
from src.service.agent.actors.mock_actor import MockAgentActor
from src.service.agent.agent_schema import AgentAction, AgentState

if TYPE_CHECKING:
    from src.service.terrarium.terrarium_schema import SimulationState


class AgentManager:
    """Agent 생성, 선택, 행동 결정 및 기억 갱신 담당."""

    SAMPLE_DATA_PATH = Path("src/service/data/actor-sample-data.json")

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

        config = getattr(ctx.cfg, "terrarium", None)
        prompt_path = str(
            getattr(config, "prompt_path", "src/service/prompts/agent_action.txt")
        )

        self.max_memories = int(getattr(config, "max_memories", 10) or 10)
        self.use_llm = bool(getattr(config, "use_llm", True))
        self.allow_mock_fallback = bool(
            getattr(config, "allow_mock_fallback", False)
        )

        # Mock은 명시적으로 use_llm=false인 테스트에서만 사용합니다.
        self.mock_actor = MockAgentActor(ctx)
        self.llm_actor = LLMAgentActor(
            ctx,
            prompt_path=prompt_path,
        )

    def create_default_agents(self) -> dict[str, AgentState]:
        agents = self._load_default_agents()
        agent_map = {agent.agent_id: agent for agent in agents}
        
        for agent in agents:
            default_relationships = {
                other.agent_id: 0
                for other in agents
                if other.agent_id != agent.agent_id
            }
            configured_relationships = {
                target_id: int(score)
                for target_id, score in agent.relationships.items()
                if target_id in default_relationships
            }
            default_relationships.update(configured_relationships)
            agent.relationships = default_relationships

        return agent_map

    def _load_default_agents(self) -> list[AgentState]:
        try:
            with self.SAMPLE_DATA_PATH.open(
                "r",
                encoding="utf-8",
            ) as file:
                raw_agents = json.load(file)
        except FileNotFoundError:
            self._log(
                "warning",
                (
                    "[ATM] Missing agent sample data: "
                    f"{self.SAMPLE_DATA_PATH}"
                ),
            )
            return []

        if not isinstance(raw_agents, list):
            raise ValueError(
                "Agent sample data must be a list"
            )

        return [
            AgentState(**agent_data)
            for agent_data in raw_agents
        ]

    def choose_actor(
        self,
        state: "SimulationState",
    ) -> AgentState:
        if not state.agents:
            raise RuntimeError(
                "Simulation has no agents"
            )

        agent_ids = list(state.agents)
        index = max(
            0,
            state.world.tick - 1,
        ) % len(agent_ids)

        return state.agents[agent_ids[index]]

    async def decide_action(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
    ) -> AgentAction:
        if not self.use_llm:
            self._log(
                "debug",
                (
                    "[ATM] mock agent selected: "
                    f"agent_id={actor.agent_id}"
                ),
            )
            return await self.mock_actor.decide(
                state=state,
                actor=actor,
            )

        try:
            action = await self.llm_actor.decide(
                state=state,
                actor=actor,
            )
            self._log(
                "info",
                (
                    "[ATM] LLM agent action: "
                    f"agent_id={actor.agent_id}, "
                    f"action={action.action.value}"
                ),
            )
            return action

        except Exception as exc:
            self._log(
                "error",
                (
                    "[ATM] LLM agent failed: "
                    f"agent_id={actor.agent_id}, "
                    f"error={type(exc).__name__}: {exc}"
                ),
            )

            if self.allow_mock_fallback:
                self._log(
                    "warning",
                    (
                        "[ATM] mock fallback enabled: "
                        f"agent_id={actor.agent_id}"
                    ),
                )
                return await self.mock_actor.decide(
                    state=state,
                    actor=actor,
                )

            # 실제 Agent 테스트 중 오류를 Mock으로 숨기지 않습니다.
            raise RuntimeError(
                (
                    "LLM Agent 행동 생성에 실패했습니다. "
                    f"agent_id={actor.agent_id}"
                )
            ) from exc

    def remember(
        self,
        actor: AgentState,
        summary: str,
    ) -> None:
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
