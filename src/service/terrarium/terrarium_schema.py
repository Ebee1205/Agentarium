from __future__ import annotations

import time
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from src.service.agent.agent_schema import AgentState
from src.service.world.world_schema import WorldState


def current_timestamp_ms() -> int:
    return time.time_ns() // 1_000_000


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def event_type_value(event_type: str | Enum) -> str:
    value = event_type.value if isinstance(event_type, Enum) else event_type
    if not isinstance(value, str) or not value.strip():
        raise ValueError("event_type must be a non-empty string")
    return value


class SimulationStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class SystemEventType(str, Enum):
    SIMULATION_CREATED = "SIMULATION_CREATED"
    SIMULATION_STARTED = "SIMULATION_STARTED"
    SIMULATION_PAUSED = "SIMULATION_PAUSED"
    SIMULATION_RESUMED = "SIMULATION_RESUMED"
    SIMULATION_STOPPED = "SIMULATION_STOPPED"
    TICK_STARTED = "TICK_STARTED"


class TerrariumEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: generate_id("evt"))
    simulation_id: str
    tick: int
    type: str
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


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Pydantic v1/v2 모델을 JSON 직렬화 가능한 dict로 변환합니다."""
    return jsonable_encoder(model)
