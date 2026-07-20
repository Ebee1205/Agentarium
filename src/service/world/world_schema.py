from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class WorldEventType(str, Enum):
    RESOURCE_CHANGED = "RESOURCE_CHANGED"
    NEED_CHANGED = "NEED_CHANGED"
    WORLD_EVENT = "WORLD_EVENT"


class LocationState(BaseModel):
    location_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""


class WorldState(BaseModel):
    tick: int = 0
    day: int = 1
    hour: int = 6
    time_of_day: str = "DAY"
    weather: str = "clear"
    tension: int = 0
    resources: dict[str, int] = Field(
        default_factory=lambda: {"food": 30, "water": 30}
    )
    locations: dict[str, LocationState] = Field(default_factory=dict)
    agent_locations: dict[str, str] = Field(default_factory=dict)
