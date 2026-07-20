from __future__ import annotations

from src.service.world.world_config import WorldRules
from src.service.world.world_schema import WorldState


class WorldClock:
    """Tick을 테라리움의 날짜·시간대로 변환합니다."""

    def __init__(self, rules: WorldRules) -> None:
        self.rules = rules

    def advance(self, world: WorldState) -> None:
        world.tick += 1
        elapsed = world.tick - 1
        world.day = (elapsed // self.rules.ticks_per_day) + 1
        world.hour = (
            self.rules.day_start_hour + elapsed
        ) % self.rules.ticks_per_day
        world.time_of_day = self._phase(world.hour)

    def _phase(self, hour: int) -> str:
        day_start = self.rules.day_start_hour
        night_start = self.rules.night_start_hour
        if day_start < night_start:
            return "DAY" if day_start <= hour < night_start else "NIGHT"
        return "NIGHT" if night_start <= hour < day_start else "DAY"
