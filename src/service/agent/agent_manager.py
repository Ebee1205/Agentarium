from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.service.agent.actors.llm_actor import LLMAgentActor
from src.service.agent.actors.mock_actor import MockAgentActor
from src.service.agent.agent_schema import (
    AgentAction,
    AgentActionType,
    AgentReply,
    AgentState,
)

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
        reply_prompt_path = str(
            getattr(
                config,
                "reply_prompt_path",
                "src/service/prompts/agent_reply.txt",
            )
        )

        self.max_memories = int(getattr(config, "max_memories", 10) or 10)
        self.max_action_history = int(
            getattr(config, "max_action_history", 8) or 8
        )
        self.max_dialogue_history = int(
            getattr(config, "max_dialogue_history", 8) or 8
        )
        self.use_llm = bool(getattr(config, "use_llm", False))
        self.allow_mock_fallback = bool(
            getattr(config, "allow_mock_fallback", False)
        )

        self.mock_actor = MockAgentActor(ctx)
        self.llm_actor = LLMAgentActor(
            ctx,
            prompt_path=prompt_path,
            reply_prompt_path=reply_prompt_path,
        )

    def create_default_agents(self) -> dict[str, AgentState]:
        agents = self._load_default_agents()
        agent_map = {agent.agent_id: agent for agent in agents}
        for agent in agents:
            previous = dict(agent.relationships)
            agent.relationships = {
                other.agent_id: int(previous.get(other.agent_id, 0))
                for other in agents
                if other.agent_id != agent.agent_id
            }
        return agent_map

    def _load_default_agents(self) -> list[AgentState]:
        try:
            with self.SAMPLE_DATA_PATH.open("r", encoding="utf-8") as file:
                raw_agents = json.load(file)
        except FileNotFoundError:
            self._log(
                "warning",
                f"[ATM] Missing agent sample data: {self.SAMPLE_DATA_PATH}",
            )
            return []

        if not isinstance(raw_agents, list):
            raise ValueError("Agent sample data must be a list")

        normalized: list[dict[str, Any]] = []
        for item in raw_agents:
            data = dict(item)
            if "location_id" not in data and "initial_location" in data:
                data["location_id"] = data.pop("initial_location")
            normalized.append(data)
        return [AgentState(**agent_data) for agent_data in normalized]

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
            action = await self.mock_actor.decide(state=state, actor=actor)
            action.source = "mock"
            self._log(
                "debug",
                f"[ATM] decision source=mock agent_id={actor.agent_id} "
                "reason=use_llm_disabled",
            )
            return action

        try:
            action = await self.llm_actor.decide(state=state, actor=actor)
            action.source = "ollama"
            self._log(
                "debug",
                f"[ATM] decision source=ollama agent_id={actor.agent_id} "
                f"action={action.action.value} narration={action.narration!r} "
                f"content={action.content!r} "
                f"relationship_delta={action.relationship_delta}",
            )
            return action
        except Exception as exc:
            self._log(
                "error",
                f"[ATM] Ollama action failed: agent_id={actor.agent_id}, "
                f"error={type(exc).__name__}: {exc}",
            )
            if not self.allow_mock_fallback:
                raise

            action = await self.mock_actor.decide(state=state, actor=actor)
            action.source = "mock-fallback"
            self._log(
                "warning",
                f"[ATM] decision source=mock-fallback agent_id={actor.agent_id}",
            )
            return action

    async def decide_reply(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
        action: AgentAction,
    ) -> AgentReply | None:
        if action.action != AgentActionType.TALK:
            return None

        target = state.agents.get(action.target_agent_id or "")
        if target is None or target.agent_id == actor.agent_id:
            return None
        if target.location_id != actor.location_id:
            return None

        if not self.use_llm:
            reply = await self.mock_actor.reply(
                state=state,
                speaker=actor,
                listener=target,
                dialogue=action.content or "",
            )
            reply_source = "mock"
        else:
            try:
                reply = await self.llm_actor.reply(
                    state=state,
                    speaker=actor,
                    listener=target,
                    dialogue=action.content or "",
                )
                reply_source = "ollama"
            except Exception as exc:
                self._log(
                    "error",
                    f"[ATM] Ollama reply failed: speaker={actor.agent_id}, "
                    f"listener={target.agent_id}, "
                    f"error={type(exc).__name__}: {exc}",
                )
                if not self.allow_mock_fallback:
                    raise
                reply = await self.mock_actor.reply(
                    state=state,
                    speaker=actor,
                    listener=target,
                    dialogue=action.content or "",
                )
                reply_source = "mock-fallback"

        action.reply_content = reply.content
        action.reply_narration = reply.narration
        action.reply_emotion = reply.emotion
        action.reply_relationship_delta = reply.relationship_delta
        action.reply_reason = reply.reason
        action.reply_source = reply_source

        self._log(
            "debug",
            f"[ATM] reply source={reply_source} speaker={actor.agent_id} "
            f"listener={target.agent_id} content={reply.content!r} "
            f"relationship_delta={reply.relationship_delta}",
        )
        return reply

    def remember(self, actor: AgentState, summary: str) -> None:
        actor.memories.append(summary)
        self._trim(actor.memories, self.max_memories)

    def record_action(self, actor: AgentState, action: AgentAction) -> None:
        target = action.target_agent_id or action.target_location_id or action.resource
        compact = action.action.value
        if target:
            compact = f"{compact}:{target}"
        actor.action_history.append(compact)
        self._trim(actor.action_history, self.max_action_history)

    def record_dialogue(
        self,
        *,
        speaker: AgentState,
        listener: AgentState,
        speaker_content: str,
        listener_content: str | None,
    ) -> None:
        speaker_line = self._dialogue_record(
            self_name=speaker.name,
            other_name=listener.name,
            self_content=speaker_content,
            other_content=listener_content,
        )
        listener_line = self._dialogue_record(
            self_name=listener.name,
            other_name=speaker.name,
            self_content=listener_content,
            other_content=speaker_content,
        )
        speaker.dialogue_history.append(speaker_line)
        listener.dialogue_history.append(listener_line)
        self._trim(speaker.dialogue_history, self.max_dialogue_history)
        self._trim(listener.dialogue_history, self.max_dialogue_history)

    def set_emotion(self, actor: AgentState, emotion: str) -> None:
        # 이전 호출부와의 호환성을 위해 남긴다.
        if emotion:
            actor.current_emotion = emotion

    @staticmethod
    def _dialogue_record(
        *,
        self_name: str,
        other_name: str,
        self_content: str | None,
        other_content: str | None,
    ) -> str:
        self_text = (self_content or "(말하지 않음)").strip()
        other_text = (other_content or "(응답 없음)").strip()
        return (
            f"{self_name}→{other_name}: {self_text} | "
            f"{other_name}→{self_name}: {other_text}"
        )

    @staticmethod
    def _trim(items: list[Any], limit: int) -> None:
        if len(items) > limit:
            del items[:-limit]

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)
        if not callable(method):
            return
        try:
            method(message)
        except TypeError:
            method("ATM", message)
