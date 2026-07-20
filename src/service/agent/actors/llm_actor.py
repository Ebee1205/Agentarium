from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.service.agent.actors.base_actor import BaseAgentActor
from src.service.agent.agent_schema import (
    AGENT_ACTION_JSON_SCHEMA,
    AGENT_REPLY_JSON_SCHEMA,
    AgentAction,
    AgentActionType,
    AgentReply,
    AgentState,
)
from src.service.terrarium.terrarium_schema import model_to_dict

if TYPE_CHECKING:
    from src.service.terrarium.terrarium_schema import SimulationState


class LLMAgentActor(BaseAgentActor):
    """LLMManager를 사용해 Agent 행동과 상호작용 응답을 생성한다."""

    MAX_ATTEMPTS = 2

    def __init__(
        self,
        ctx: Any,
        prompt_path: str,
        reply_prompt_path: str,
    ) -> None:
        super().__init__(ctx)
        self.prompt_path = Path(prompt_path)
        self.reply_prompt_path = Path(reply_prompt_path)

    async def decide(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
    ) -> AgentAction:
        manager = self._manager()
        prompt = self._load_prompt(self.prompt_path)

        other_agents = [
            model_to_dict(agent)
            for agent in state.agents.values()
            if agent.agent_id != actor.agent_id
        ]
        nearby_agents = [
            item for item in other_agents if item.get("location_id") == actor.location_id
        ]

        validation_error: str | None = None
        for _attempt in range(1, self.MAX_ATTEMPTS + 1):
            prompts: list[str] = [prompt]
            if validation_error:
                prompts.append(
                    "[이전 응답 수정 요청]\n"
                    f"{validation_error}\n"
                    "규칙을 다시 확인하고 올바른 JSON만 반환하세요."
                )

            payload = await manager.generate_json(
                prompts,
                placeholders={
                    "agent": model_to_dict(actor),
                    "world": model_to_dict(state.world),
                    "other_agents": other_agents,
                    "nearby_agents": nearby_agents,
                },
                response_schema=AGENT_ACTION_JSON_SCHEMA,
                temperature=0.55,
                max_output_tokens=640,
                num_ctx=8192,
                keep_alive="10m",
                think=False,
            )
            self._log_payload("action", actor.agent_id, payload)

            if not isinstance(payload, dict):
                validation_error = "Agent action must be a JSON object"
                continue

            try:
                action = self._validate_model(AgentAction, payload)
                self._validate_action(state=state, actor=actor, action=action)
                return action
            except Exception as exc:
                validation_error = f"{type(exc).__name__}: {exc}"

        raise ValueError(
            "LLM이 유효한 AgentAction을 생성하지 못했습니다: "
            f"{validation_error}"
        )

    async def reply(
        self,
        *,
        state: "SimulationState",
        speaker: AgentState,
        listener: AgentState,
        dialogue: str,
    ) -> AgentReply:
        if not dialogue.strip():
            raise ValueError("상대 Agent에게 전달할 대사가 비어 있습니다.")
        if speaker.location_id != listener.location_id:
            raise ValueError("서로 다른 장소에 있는 Agent끼리는 대화할 수 없습니다.")

        manager = self._manager()
        payload = await manager.generate_json(
            self._load_prompt(self.reply_prompt_path),
            placeholders={
                "speaker": model_to_dict(speaker),
                "listener": model_to_dict(listener),
                "dialogue": dialogue,
                "world": model_to_dict(state.world),
                "relationship": listener.relationships.get(speaker.agent_id, 0),
            },
            response_schema=AGENT_REPLY_JSON_SCHEMA,
            temperature=0.65,
            max_output_tokens=384,
            num_ctx=8192,
            keep_alive="10m",
            think=False,
        )
        self._log_payload("reply", listener.agent_id, payload)

        if not isinstance(payload, dict):
            raise ValueError("Agent reply must be a JSON object")

        reply = self._validate_model(AgentReply, payload)
        if reply.content.strip() == dialogue.strip():
            raise ValueError("응답 Agent가 상대 대사를 그대로 반복했습니다.")
        return reply

    @staticmethod
    def _validate_action(
        *,
        state: "SimulationState",
        actor: AgentState,
        action: AgentAction,
    ) -> None:
        if not action.narration.strip():
            raise ValueError("narration이 비어 있습니다.")

        if action.action == AgentActionType.MOVE:
            target = action.target_location_id
            if target not in state.world.locations:
                raise ValueError("MOVE.target_location_id가 월드 locations에 없습니다.")
            if target == actor.location_id:
                raise ValueError("MOVE 대상은 현재 위치와 달라야 합니다.")

        if action.action == AgentActionType.TALK:
            target_id = action.target_agent_id
            target = state.agents.get(target_id or "")
            if target is None:
                raise ValueError("TALK.target_agent_id가 다른 Agent 목록에 없습니다.")
            if target.agent_id == actor.agent_id:
                raise ValueError("Agent는 자기 자신과 TALK할 수 없습니다.")
            if target.location_id != actor.location_id:
                raise ValueError("TALK 대상은 현재 같은 장소에 있어야 합니다.")
            if not action.content or not action.content.strip():
                raise ValueError("TALK.content가 비어 있습니다.")
        elif action.content is not None:
            raise ValueError("TALK가 아닌 행동의 content는 null이어야 합니다.")

        if action.action == AgentActionType.USE_RESOURCE:
            resource = action.resource
            if resource not in {"food", "water"}:
                raise ValueError("USE_RESOURCE.resource는 food 또는 water여야 합니다.")
            if state.world.resources.get(resource, 0) <= 0:
                raise ValueError(f"사용할 수 없는 자원입니다: {resource}")

    def _manager(self) -> Any:
        manager = getattr(self.ctx, "llm_manager", None)
        if manager is None:
            raise RuntimeError("LLMManager is not initialized")
        return manager

    @staticmethod
    def _validate_model(model_class: Any, payload: dict[str, Any]) -> Any:
        if hasattr(model_class, "model_validate"):
            return model_class.model_validate(payload)
        return model_class.parse_obj(payload)

    @staticmethod
    def _load_prompt(path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"Agent prompt not found: {path}")
        return path.read_text(encoding="utf-8")

    def _log_payload(self, kind: str, agent_id: str, payload: Any) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, "debug", None)
        if not callable(method):
            return
        message = (
            f"[ATM][OLLAMA] kind={kind} agent_id={agent_id} "
            f"payload={json.dumps(payload, ensure_ascii=False, default=str)}"
        )
        try:
            method(message)
        except TypeError:
            method("ATM", message)
