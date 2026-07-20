from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
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

    MAX_ATTEMPTS = 3
    DUPLICATE_THRESHOLD = 0.86

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
            self._public_agent_view(actor, agent)
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
                    "직전 문장과 다른 행동 또는 새로운 문장을 선택하고, "
                    "규칙에 맞는 JSON만 반환하세요."
                )

            payload = await manager.generate_json(
                prompts,
                placeholders={
                    "agent": model_to_dict(actor),
                    "world": model_to_dict(state.world),
                    "other_agents": other_agents,
                    "nearby_agents": nearby_agents,
                    "recent_actions": actor.action_history[-6:],
                    "recent_dialogues": actor.dialogue_history[-6:],
                },
                response_schema=AGENT_ACTION_JSON_SCHEMA,
                temperature=0.72,
                max_output_tokens=700,
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
                self._clean_action(action)
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
        dialogue = self._strip_dialogue_quotes(dialogue)
        if not dialogue.strip():
            raise ValueError("상대 Agent에게 전달할 대사가 비어 있습니다.")
        if speaker.location_id != listener.location_id:
            raise ValueError("서로 다른 장소에 있는 Agent끼리는 대화할 수 없습니다.")

        manager = self._manager()
        validation_error: str | None = None
        for _attempt in range(1, self.MAX_ATTEMPTS + 1):
            prompts: list[str] = [self._load_prompt(self.reply_prompt_path)]
            if validation_error:
                prompts.append(
                    "[이전 응답 수정 요청]\n"
                    f"{validation_error}\n"
                    "상대의 문장이나 최근 자신의 대사를 복사하지 말고, "
                    "자신의 관점에서 새로운 응답 JSON만 반환하세요."
                )

            payload = await manager.generate_json(
                prompts,
                placeholders={
                    "speaker": self._public_agent_view(listener, speaker),
                    "listener": model_to_dict(listener),
                    "dialogue": dialogue,
                    "world": model_to_dict(state.world),
                    "relationship": listener.relationships.get(speaker.agent_id, 0),
                    "recent_actions": listener.action_history[-6:],
                    "recent_dialogues": listener.dialogue_history[-6:],
                },
                response_schema=AGENT_REPLY_JSON_SCHEMA,
                temperature=0.78,
                max_output_tokens=440,
                num_ctx=8192,
                keep_alive="10m",
                think=False,
            )
            self._log_payload("reply", listener.agent_id, payload)

            if not isinstance(payload, dict):
                validation_error = "Agent reply must be a JSON object"
                continue

            try:
                reply = self._validate_model(AgentReply, payload)
                self._clean_reply(reply)
                self._validate_reply(
                    listener=listener,
                    dialogue=dialogue,
                    reply=reply,
                )
                return reply
            except Exception as exc:
                validation_error = f"{type(exc).__name__}: {exc}"

        raise ValueError(
            "LLM이 유효한 AgentReply를 생성하지 못했습니다: "
            f"{validation_error}"
        )

    def _validate_action(
        self,
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
            if self._is_recent_duplicate(action.content, actor.dialogue_history):
                raise ValueError("최근 대화와 지나치게 유사한 TALK.content입니다.")
            last_action = actor.action_history[-1] if actor.action_history else ""
            if last_action == f"TALK:{target_id}":
                raise ValueError("직전 행동과 같은 상대에게 연속 TALK할 수 없습니다.")
        else:
            if action.content is not None:
                raise ValueError("TALK가 아닌 행동의 content는 null이어야 합니다.")
            if action.relationship_delta != 0:
                raise ValueError(
                    "TALK가 아닌 행동의 relationship_delta는 0이어야 합니다."
                )

        if action.action == AgentActionType.USE_RESOURCE:
            resource = action.resource
            if resource not in {"food", "water"}:
                raise ValueError("USE_RESOURCE.resource는 food 또는 water여야 합니다.")
            if state.world.resources.get(resource, 0) <= 0:
                raise ValueError(f"사용할 수 없는 자원입니다: {resource}")

        recent_types = [
            item.split(":", 1)[0]
            for item in actor.action_history[-2:]
        ]
        if (
            len(recent_types) == 2
            and all(item == action.action.value for item in recent_types)
            and action.action in {
                AgentActionType.OBSERVE,
                AgentActionType.WAIT,
                AgentActionType.TALK,
            }
        ):
            raise ValueError(
                f"{action.action.value} 행동을 세 번 연속 선택할 수 없습니다."
            )

    def _validate_reply(
        self,
        *,
        listener: AgentState,
        dialogue: str,
        reply: AgentReply,
    ) -> None:
        if self._similar(dialogue, reply.content) >= self.DUPLICATE_THRESHOLD:
            raise ValueError("응답 Agent가 상대 대사를 그대로 반복했습니다.")
        if self._is_recent_duplicate(reply.content, listener.dialogue_history):
            raise ValueError("응답 Agent가 최근 자신의 대사를 반복했습니다.")
        if not reply.narration.strip():
            raise ValueError("reply.narration이 비어 있습니다.")

    @staticmethod
    def _public_agent_view(viewer: AgentState, agent: AgentState) -> dict[str, Any]:
        """다른 Agent의 비밀·목표·기억이 프롬프트로 누출되지 않게 한다."""
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "personality": dict(agent.personality),
            "location_id": agent.location_id,
            "current_emotion": agent.current_emotion,
            "relationship_from_me": viewer.relationships.get(agent.agent_id, 0),
        }

    @classmethod
    def _clean_action(cls, action: AgentAction) -> None:
        action.narration = cls._clean_sentence(action.narration)
        action.reason = cls._clean_sentence(action.reason)
        action.emotion = cls._clean_token(action.emotion)
        if action.content is not None:
            action.content = cls._strip_dialogue_quotes(action.content)

    @classmethod
    def _clean_reply(cls, reply: AgentReply) -> None:
        reply.narration = cls._clean_sentence(reply.narration)
        reply.reason = cls._clean_sentence(reply.reason)
        reply.emotion = cls._clean_token(reply.emotion)
        reply.content = cls._strip_dialogue_quotes(reply.content)

    @staticmethod
    def _clean_sentence(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @classmethod
    def _clean_token(cls, value: str) -> str:
        return cls._clean_sentence(value).strip('"\'“”‘’') or "neutral"

    @classmethod
    def _strip_dialogue_quotes(cls, value: str) -> str:
        text = cls._clean_sentence(value)
        previous = None
        while text and text != previous:
            previous = text
            text = text.strip()
            if len(text) >= 2 and (
                (text[0], text[-1])
                in {
                    ('"', '"'),
                    ("'", "'"),
                    ('“', '”'),
                    ('‘', '’'),
                }
            ):
                text = text[1:-1].strip()
        return text.rstrip('"\'”’').lstrip('"\'“‘').strip()

    def _is_recent_duplicate(self, content: str, history: list[str]) -> bool:
        for item in history[-6:]:
            for candidate in self._extract_dialogue_fragments(item):
                if self._similar(content, candidate) >= self.DUPLICATE_THRESHOLD:
                    return True
        return False

    @classmethod
    def _extract_dialogue_fragments(cls, item: str) -> list[str]:
        fragments: list[str] = []
        for segment in str(item).split("|"):
            if ":" in segment:
                _, value = segment.split(":", 1)
                value = cls._strip_dialogue_quotes(value)
                if value and not value.startswith("("):
                    fragments.append(value)
        if not fragments:
            fragments.append(cls._strip_dialogue_quotes(item))
        return fragments

    @classmethod
    def _similar(cls, left: str, right: str) -> float:
        a = cls._normalize(left)
        b = cls._normalize(right)
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(value or "")).lower()

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
