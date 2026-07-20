from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentActionType(str, Enum):
    TALK = "TALK"
    MOVE = "MOVE"
    OBSERVE = "OBSERVE"
    USE_RESOURCE = "USE_RESOURCE"
    WAIT = "WAIT"


class AgentState(BaseModel):
    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    personality: dict[str, int] = Field(default_factory=dict)
    needs: dict[str, int] = Field(
        default_factory=lambda: {
            "hunger": 20,
            "energy": 80,
            "loneliness": 20,
        }
    )
    location_id: str = "nest"
    current_emotion: str = "calm"
    relationships: dict[str, int] = Field(default_factory=dict)
    memories: list[str] = Field(default_factory=list)
    action_history: list[str] = Field(default_factory=list)
    dialogue_history: list[str] = Field(default_factory=list)
    goal: str = "오늘 하루를 무사히 보낸다."
    secret: str | None = None


class AgentAction(BaseModel):
    action: AgentActionType
    target_agent_id: str | None = None
    target_location_id: str | None = None
    resource: str | None = None

    narration: str = ""
    content: str | None = None
    emotion: str = "neutral"
    relationship_delta: int = Field(default=0, ge=-3, le=3)
    reason: str = ""

    # 서버 내부 메타데이터. LLM 응답 스키마에는 포함하지 않는다.
    source: str = Field(default="unknown", exclude=True)
    reply_content: str | None = Field(default=None, exclude=True)
    reply_narration: str | None = Field(default=None, exclude=True)
    reply_emotion: str | None = Field(default=None, exclude=True)
    reply_relationship_delta: int = Field(default=0, exclude=True)
    reply_reason: str | None = Field(default=None, exclude=True)
    reply_source: str | None = Field(default=None, exclude=True)


class AgentReply(BaseModel):
    narration: str = Field(min_length=1)
    content: str = Field(min_length=1)
    emotion: str = Field(min_length=1)
    relationship_delta: int = Field(default=0, ge=-3, le=3)
    reason: str = Field(min_length=1)


AGENT_ACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [item.value for item in AgentActionType],
        },
        "target_agent_id": {"type": ["string", "null"]},
        "target_location_id": {"type": ["string", "null"]},
        "resource": {"type": ["string", "null"]},
        "narration": {"type": "string"},
        "content": {"type": ["string", "null"]},
        "emotion": {"type": "string"},
        "relationship_delta": {
            "type": "integer",
            "minimum": -3,
            "maximum": 3,
        },
        "reason": {"type": "string"},
    },
    "required": [
        "action",
        "target_agent_id",
        "target_location_id",
        "resource",
        "narration",
        "content",
        "emotion",
        "relationship_delta",
        "reason",
    ],
    "additionalProperties": False,
}


AGENT_REPLY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "narration": {"type": "string"},
        "content": {"type": "string"},
        "emotion": {"type": "string"},
        "relationship_delta": {
            "type": "integer",
            "minimum": -3,
            "maximum": 3,
        },
        "reason": {"type": "string"},
    },
    "required": [
        "narration",
        "content",
        "emotion",
        "relationship_delta",
        "reason",
    ],
    "additionalProperties": False,
}
