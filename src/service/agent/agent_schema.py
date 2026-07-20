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
    goal: str = "오늘 하루를 무사히 보낸다."
    secret: str | None = None


class AgentAction(BaseModel):
    action: AgentActionType
    target_agent_id: str | None = None
    target_location_id: str | None = None
    resource: str | None = None
    content: str | None = None
    emotion: str = "neutral"
    reason: str = ""


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
        "content": {"type": ["string", "null"]},
        "emotion": {"type": "string"},
        "reason": {"type": "string"},
    },
    # 모든 키를 누락 없이 응답하도록 required에 전부 포함
    "required": [
        "action", 
        "target_agent_id", 
        "target_location_id", 
        "resource", 
        "content", 
        "emotion", 
        "reason"
    ],
    "additionalProperties": False,
}