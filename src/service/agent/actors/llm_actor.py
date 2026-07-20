from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.service.agent.actors.base_actor import BaseAgentActor
from src.service.agent.agent_schema import (
    AGENT_ACTION_JSON_SCHEMA,
    AgentAction,
    AgentState,
)
from src.service.terrarium.terrarium_schema import model_to_dict

if TYPE_CHECKING:
    from src.service.terrarium.terrarium_schema import SimulationState


class LLMAgentActor(BaseAgentActor):
    """LLMManager를 사용해 Agent 행동 의도를 생성하는 Actor."""

    def __init__(self, ctx: Any, prompt_path: str) -> None:
        super().__init__(ctx)
        self.prompt_path = Path(prompt_path)

    async def decide(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
    ) -> AgentAction:
        manager = getattr(self.ctx, "llm_manager", None)
        if manager is None:
            raise RuntimeError("LLMManager is not initialized")

        payload = await manager.generate_json(
            self._load_prompt(),
            placeholders={
                "agent": model_to_dict(actor),
                "world": model_to_dict(state.world),
                "other_agents": [
                    model_to_dict(agent)
                    for agent in state.agents.values()
                    if agent.agent_id != actor.agent_id
                ],
            },
            response_schema=AGENT_ACTION_JSON_SCHEMA,
            temperature=0.8,
        )
        if not isinstance(payload, dict):
            raise ValueError("Agent action must be a JSON object")

        if hasattr(AgentAction, "model_validate"):
            return AgentAction.model_validate(payload)
        return AgentAction.parse_obj(payload)

    def _load_prompt(self) -> str:
        if not self.prompt_path.exists():
            raise FileNotFoundError(f"Agent prompt not found: {self.prompt_path}")
        return self.prompt_path.read_text(encoding="utf-8")
