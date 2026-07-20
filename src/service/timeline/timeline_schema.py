from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.service.terrarium.terrarium_schema import current_timestamp_ms, generate_id


class TimelineCategory(str, Enum):
    SYSTEM = "SYSTEM"
    AGENT = "AGENT"
    WORLD = "WORLD"
    RESOURCE = "RESOURCE"
    RELATIONSHIP = "RELATIONSHIP"


class TimelineItem(BaseModel):
    timeline_id: str = Field(default_factory=lambda: generate_id("tl"))
    simulation_id: str
    tick: int
    category: TimelineCategory
    source_event_type: str
    title: str
    summary: str
    importance: int = Field(default=1, ge=1, le=5)
    actor_id: str | None = None
    target_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: int = Field(default_factory=current_timestamp_ms)
