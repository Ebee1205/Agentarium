from __future__ import annotations

import json
from pathlib import Path
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


LOCATION_SAMPLE_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "location-sample-data.json"


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
    try:
        with LOCATION_SAMPLE_DATA_PATH.open("r", encoding="utf-8") as file:
            raw_locations = json.load(file)
    except FileNotFoundError:
        return {}

    if not isinstance(raw_locations, list):
        raise ValueError("Location sample data must be a list")

    locations = [LocationState(**location_data) for location_data in raw_locations]
    return {location.location_id: location for location in locations}
