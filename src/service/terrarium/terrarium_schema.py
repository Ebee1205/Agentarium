from __future__ import annotations

import time
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field


def current_timestamp_ms() -> int:
    return time.time_ns() // 1_000_000


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SimulationStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class AgentActionType(str, Enum):
    TALK = "TALK"
    MOVE = "MOVE"
    OBSERVE = "OBSERVE"
    USE_RESOURCE = "USE_RESOURCE"
    WAIT = "WAIT"


class TerrariumEventType(str, Enum):
    SIMULATION_CREATED = "SIMULATION_CREATED"
    SIMULATION_STARTED = "SIMULATION_STARTED"
    SIMULATION_PAUSED = "SIMULATION_PAUSED"
    SIMULATION_RESUMED = "SIMULATION_RESUMED"
    SIMULATION_STOPPED = "SIMULATION_STOPPED"
    TICK_STARTED = "TICK_STARTED"
    AGENT_TALKED = "AGENT_TALKED"
    AGENT_MOVED = "AGENT_MOVED"
    AGENT_OBSERVED = "AGENT_OBSERVED"
    AGENT_WAITED = "AGENT_WAITED"
    RESOURCE_CHANGED = "RESOURCE_CHANGED"
    NEED_CHANGED = "NEED_CHANGED"
    RELATIONSHIP_CHANGED = "RELATIONSHIP_CHANGED"
    WORLD_EVENT = "WORLD_EVENT"


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


class LocationState(BaseModel):
    location_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""


class WorldState(BaseModel):
    tick: int = 0
    time_of_day: str = "DAY"
    weather: str = "clear"
    tension: int = 0
    resources: dict[str, int] = Field(
        default_factory=lambda: {"food": 30, "water": 30}
    )
    locations: dict[str, LocationState] = Field(default_factory=dict)
    agent_locations: dict[str, str] = Field(default_factory=dict)


class AgentAction(BaseModel):
    action: AgentActionType
    target_agent_id: str | None = None
    target_location_id: str | None = None
    resource: str | None = None
    content: str | None = None
    emotion: str = "neutral"
    reason: str = ""


class TerrariumEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: generate_id("evt"))
    simulation_id: str
    tick: int
    type: TerrariumEventType
    actor_id: str | None = None
    target_id: str | None = None
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: int = Field(default_factory=current_timestamp_ms)


class SimulationState(BaseModel):
    simulation_id: str
    name: str = "ATM Terrarium"
    status: SimulationStatus = SimulationStatus.CREATED
    tick_seconds: float = Field(default=3.0, ge=0.2, le=3600)
    world: WorldState
    agents: dict[str, AgentState]
    created_at: int = Field(default_factory=current_timestamp_ms)
    updated_at: int = Field(default_factory=current_timestamp_ms)


class CreateSimulationRequest(BaseModel):
    simulation_id: str | None = None
    name: str = "ATM Terrarium"
    tick_seconds: float | None = Field(default=None, ge=0.2, le=3600)
    agents: list[AgentState] | None = None


class ObserverInterventionRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=300)
    data: dict[str, Any] = Field(default_factory=dict)


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
    "required": ["action", "emotion", "reason"],
    "additionalProperties": False,
}


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Pydantic v1/v2 모델을 Enum까지 JSON 직렬화 가능한 dict로 변환합니다."""
    return jsonable_encoder(model)
