from __future__ import annotations

import asyncio
from typing import Any

from src.service.agent.agent_manager import AgentManager
from src.service.terrarium.event_manager import EventManager
from src.service.terrarium.terrarium_schema import (
    CreateSimulationRequest,
    SimulationState,
    SimulationStatus,
    SystemEventType,
    current_timestamp_ms,
    generate_id,
    model_to_dict,
)
from src.service.world.world_manager import WorldManager
from src.service.world.world_schema import WorldEventType


class SimulationManager:
    """ATM 테라리움 생성, 제어 및 Tick 루프를 조율합니다."""

    def __init__(
        self,
        ctx: Any,
        *,
        agent_manager: AgentManager,
        world_manager: WorldManager,
        event_manager: EventManager,
    ) -> None:
        self.ctx = ctx
        self.agent_manager = agent_manager
        self.world_manager = world_manager
        self.event_manager = event_manager
        self.simulations: dict[str, SimulationState] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def create(
        self,
        request: CreateSimulationRequest | None = None,
    ) -> SimulationState:
        request = request or CreateSimulationRequest()
        simulation_id = request.simulation_id or generate_id("sim")
        if simulation_id in self.simulations:
            raise ValueError(f"Simulation already exists: {simulation_id}")

        agents = (
            {agent.agent_id: agent for agent in request.agents}
            if request.agents
            else self.agent_manager.create_default_agents()
        )
        config = getattr(self.ctx.cfg, "terrarium", None)
        tick_seconds = request.tick_seconds or float(
            getattr(config, "tick_seconds", 3.0) or 3.0
        )
        state = SimulationState(
            simulation_id=simulation_id,
            name=request.name,
            tick_seconds=tick_seconds,
            world=self.world_manager.create_world(agents),
            agents=agents,
        )
        self.simulations[simulation_id] = state
        self.locks[simulation_id] = asyncio.Lock()

        await self.event_manager.emit(
            simulation_id=simulation_id,
            tick=0,
            event_type=SystemEventType.SIMULATION_CREATED,
            summary=f"‘{state.name}’ 테라리움이 생성되었다.",
            payload={"agent_ids": list(agents)},
        )
        return state

    async def ensure(self, simulation_id: str) -> SimulationState:
        state = self.simulations.get(simulation_id)
        if state is not None:
            return state
        return await self.create(CreateSimulationRequest(simulation_id=simulation_id))

    def get(self, simulation_id: str) -> SimulationState:
        state = self.simulations.get(simulation_id)
        if state is None:
            raise KeyError(f"Simulation not found: {simulation_id}")
        return state

    async def start(self, simulation_id: str, *, resumed: bool = False) -> SimulationState:
        state = await self.ensure(simulation_id)
        if state.status == SimulationStatus.RUNNING:
            return state

        was_paused = state.status == SimulationStatus.PAUSED
        state.status = SimulationStatus.RUNNING
        state.updated_at = current_timestamp_ms()
        is_resume = resumed or was_paused
        await self.event_manager.emit(
            simulation_id=simulation_id,
            tick=state.world.tick,
            event_type=(
                SystemEventType.SIMULATION_RESUMED
                if is_resume
                else SystemEventType.SIMULATION_STARTED
            ),
            summary=(
                "테라리움의 시간이 다시 흐르기 시작했다."
                if is_resume
                else "테라리움 시뮬레이션이 시작되었다."
            ),
        )

        task = self.tasks.get(simulation_id)
        if task is None or task.done():
            self.tasks[simulation_id] = asyncio.create_task(
                self._run_loop(simulation_id),
                name=f"atm-terrarium-{simulation_id}",
            )
        return state

    async def pause(self, simulation_id: str) -> SimulationState:
        state = self.get(simulation_id)
        if state.status != SimulationStatus.RUNNING:
            return state
        state.status = SimulationStatus.PAUSED
        state.updated_at = current_timestamp_ms()
        await self.event_manager.emit(
            simulation_id=simulation_id,
            tick=state.world.tick,
            event_type=SystemEventType.SIMULATION_PAUSED,
            summary="관찰자가 테라리움의 시간을 일시 정지했다.",
        )
        return state

    async def stop(self, simulation_id: str) -> SimulationState:
        state = self.get(simulation_id)
        if state.status == SimulationStatus.STOPPED:
            return state
        state.status = SimulationStatus.STOPPED
        state.updated_at = current_timestamp_ms()
        await self.event_manager.emit(
            simulation_id=simulation_id,
            tick=state.world.tick,
            event_type=SystemEventType.SIMULATION_STOPPED,
            summary="테라리움 시뮬레이션이 종료되었다.",
        )
        task = self.tasks.pop(simulation_id, None)
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return state

    async def run_tick(self, simulation_id: str) -> SimulationState:
        state = await self.ensure(simulation_id)
        lock = self.locks.setdefault(simulation_id, asyncio.Lock())
        async with lock:
            world_events = self.world_manager.advance(state.world)
            state.updated_at = current_timestamp_ms()

            await self.event_manager.emit(
                simulation_id=simulation_id,
                tick=state.world.tick,
                event_type=SystemEventType.TICK_STARTED,
                summary=(
                    f"Day {state.world.day}, {state.world.hour:02d}:00 — "
                    f"{state.world.time_of_day.lower()} 시간이 시작되었다."
                ),
                payload={
                    "day": state.world.day,
                    "hour": state.world.hour,
                    "time_of_day": state.world.time_of_day,
                    "weather": state.world.weather,
                },
            )

            for item in world_events:
                await self.event_manager.emit(
                    simulation_id=simulation_id,
                    tick=state.world.tick,
                    event_type=item["event_type"],
                    summary=item["summary"],
                    payload=item.get("payload", {}),
                )

            self.world_manager.apply_passive_needs(
                state.agents,
                state.world.time_of_day,
            )
            actor = self.agent_manager.choose_actor(state)
            action = await self.agent_manager.decide_action(state=state, actor=actor)
            self.agent_manager.set_emotion(actor, action.emotion)
            result = self.world_manager.resolve_action(
                world=state.world,
                agents=state.agents,
                actor=actor,
                action=action,
            )
            self.agent_manager.remember(actor, result["summary"])
            await self.event_manager.emit(
                simulation_id=simulation_id,
                tick=state.world.tick,
                event_type=result["event_type"],
                summary=result["summary"],
                actor_id=actor.agent_id,
                target_id=result.get("target_id"),
                payload={
                    **result.get("payload", {}),
                    "action": action.action.value,
                },
            )
            return state

    async def intervene(
        self,
        simulation_id: str,
        *,
        summary: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        state = await self.ensure(simulation_id)
        await self.event_manager.emit(
            simulation_id=simulation_id,
            tick=state.world.tick,
            event_type=WorldEventType.WORLD_EVENT,
            summary=summary,
            actor_id="observer",
            payload=data or {},
        )

    def snapshot(self, simulation_id: str) -> dict[str, Any]:
        return model_to_dict(self.get(simulation_id))

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        self.tasks.clear()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_loop(self, simulation_id: str) -> None:
        try:
            while True:
                state = self.simulations.get(simulation_id)
                if state is None or state.status == SimulationStatus.STOPPED:
                    return
                if state.status == SimulationStatus.PAUSED:
                    await asyncio.sleep(0.25)
                    continue
                await self.run_tick(simulation_id)
                await asyncio.sleep(state.tick_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log("error", f"[ATM] simulation loop failed: {exc}")
            state = self.simulations.get(simulation_id)
            if state is not None:
                state.status = SimulationStatus.STOPPED

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ctx, "log", None)
        method = getattr(logger, level, None)
        if not callable(method):
            return
        try:
            method(message)
        except TypeError:
            method("ATM", message)
