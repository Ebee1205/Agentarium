from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.service.agent.actors.base_actor import BaseAgentActor
from src.service.agent.agent_schema import (
    AGENT_ACTION_JSON_SCHEMA,
    AgentAction,
    AgentActionType,
    AgentState,
)
from src.service.terrarium.terrarium_schema import model_to_dict

if TYPE_CHECKING:
    from src.service.terrarium.terrarium_schema import SimulationState


class LLMAgentActor(BaseAgentActor):
    """LLMManager를 사용해 Agent 행동 의도를 생성하는 Actor."""

    MAX_ATTEMPTS = 2

    def __init__(
        self,
        ctx: Any,
        prompt_path: str,
    ) -> None:
        super().__init__(ctx)
        self.prompt_path = Path(prompt_path)

    async def decide(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
    ) -> AgentAction:
        manager = getattr(
            self.ctx,
            "llm_manager",
            None,
        )

        if manager is None:
            raise RuntimeError(
                "LLMManager is not initialized"
            )

        prompt = self._load_prompt()
        validation_error: str | None = None

        for attempt in range(
            1,
            self.MAX_ATTEMPTS + 1,
        ):
            prompts: list[str] = [prompt]

            if validation_error:
                prompts.append(
                    (
                        "[이전 응답 수정 요청]\n"
                        f"{validation_error}\n"
                        "규칙을 다시 확인하고 올바른 JSON만 반환하세요."
                    )
                )

            payload = await manager.generate_json(
                prompts,
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
                temperature=0.45,
                max_output_tokens=512,
                num_ctx=8192,
                keep_alive="10m",
                think=False,
            )

            if not isinstance(payload, dict):
                validation_error = (
                    "Agent action must be a JSON object"
                )
                continue

            try:
                if hasattr(AgentAction, "model_validate"):
                    action = AgentAction.model_validate(
                        payload
                    )
                else:
                    action = AgentAction.parse_obj(
                        payload
                    )

                self._validate_action(
                    state=state,
                    actor=actor,
                    action=action,
                )
                return action

            except Exception as exc:
                validation_error = (
                    f"{type(exc).__name__}: {exc}"
                )

        raise ValueError(
            (
                "LLM이 유효한 AgentAction을 생성하지 못했습니다: "
                f"{validation_error}"
            )
        )

    @staticmethod
    def _validate_action(
        *,
        state: "SimulationState",
        actor: AgentState,
        action: AgentAction,
    ) -> None:
        if action.action == AgentActionType.MOVE:
            target = action.target_location_id

            if target not in state.world.locations:
                raise ValueError(
                    (
                        "MOVE.target_location_id가 "
                        "월드 locations에 없습니다."
                    )
                )

            if target == actor.location_id:
                raise ValueError(
                    "MOVE 대상은 현재 위치와 달라야 합니다."
                )

        if action.action == AgentActionType.TALK:
            target_id = action.target_agent_id
            target = state.agents.get(
                target_id or ""
            )

            if target is None:
                raise ValueError(
                    (
                        "TALK.target_agent_id가 "
                        "다른 Agent 목록에 없습니다."
                    )
                )

            if target.agent_id == actor.agent_id:
                raise ValueError(
                    "Agent는 자기 자신과 TALK할 수 없습니다."
                )

            if not action.content:
                raise ValueError(
                    "TALK.content가 비어 있습니다."
                )

        if action.action == AgentActionType.USE_RESOURCE:
            resource = action.resource

            if resource not in {"food", "water"}:
                raise ValueError(
                    (
                        "USE_RESOURCE.resource는 "
                        "food 또는 water여야 합니다."
                    )
                )

            if state.world.resources.get(
                resource,
                0,
            ) <= 0:
                raise ValueError(
                    (
                        f"사용할 수 없는 자원입니다: "
                        f"{resource}"
                    )
                )

    def _load_prompt(self) -> str:
        if not self.prompt_path.exists():
            raise FileNotFoundError(f"Agent prompt not found: {self.prompt_path}")
        return self.prompt_path.read_text(encoding="utf-8")
