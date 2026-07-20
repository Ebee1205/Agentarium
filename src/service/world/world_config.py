from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.service.world.world_schema import LocationState


class WorldRules(BaseModel):
    ticks_per_day: int = Field(default=24, ge=4)
    day_start_hour: int = Field(default=6, ge=0, le=23)
    night_start_hour: int = Field(default=18, ge=0, le=23)
    initial_food: int = Field(default=30, ge=0)
    initial_water: int = Field(default=30, ge=0)
    hunger_per_tick: int = Field(default=2, ge=0)
    energy_day_cost: int = Field(default=1, ge=0)
    energy_night_cost: int = Field(default=2, ge=0)


def load_world_rules(ctx: Any) -> WorldRules:
    config = getattr(getattr(ctx, "cfg", None), "terrarium", None)
    return WorldRules(
        ticks_per_day=int(getattr(config, "ticks_per_day", 24) or 24),
        day_start_hour=int(getattr(config, "day_start_hour", 6) or 6),
        night_start_hour=int(getattr(config, "night_start_hour", 18) or 18),
        initial_food=int(getattr(config, "initial_food", 30) or 0),
        initial_water=int(getattr(config, "initial_water", 30) or 0),
        hunger_per_tick=int(getattr(config, "hunger_per_tick", 2) or 0),
        energy_day_cost=int(getattr(config, "energy_day_cost", 1) or 0),
        energy_night_cost=int(getattr(config, "energy_night_cost", 2) or 0),
    )


def default_locations() -> dict[str, LocationState]:
    return {
        "home": LocationState(
            location_id="home",
            name="집",
            description="개체들이 쉬거나 대화하는 안전한 장소",
        ),
        "pond": LocationState(
            location_id="pond",
            name="연못",
            description="물을 구하거나 수상한 흔적을 발견할 수 있는 장소",
        ),
        "storage": LocationState(
            location_id="storage",
            name="식량 보관소",
            description="공동 식량이 쌓여 있는 장소",
        ),
    }
