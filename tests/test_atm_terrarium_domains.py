import asyncio
from types import SimpleNamespace

from src.service.agent.agent_manager import AgentManager
from src.service.terrarium.event_manager import EventManager
from src.service.terrarium.simulation_manager import SimulationManager
from src.service.timeline.timeline_service import TimelineService
from src.service.world.world_manager import WorldManager


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _WebSocketHandler:
    def __init__(self):
        self.messages = []

    async def broadcast_to_session(self, sid, message):
        self.messages.append((sid, message))
        return 1


def _context():
    terrarium = SimpleNamespace(
        tick_seconds=0.2,
        max_events=200,
        use_llm=False,
        prompt_path="src/service/prompts/agent_action.txt",
        max_memories=10,
        ticks_per_day=24,
        day_start_hour=6,
        night_start_hour=18,
        initial_food=30,
        initial_water=30,
        hunger_per_tick=2,
        energy_day_cost=1,
        energy_night_cost=2,
    )
    return SimpleNamespace(
        cfg=SimpleNamespace(terrarium=terrarium),
        log=_Logger(),
        ws_handler=_WebSocketHandler(),
        llm_manager=None,
    )


def test_domain_managers_generate_matching_events_and_timeline():
    async def scenario():
        ctx = _context()
        timeline = TimelineService(ctx)
        events = EventManager(ctx, timeline_service=timeline)
        manager = SimulationManager(
            ctx,
            agent_manager=AgentManager(ctx),
            world_manager=WorldManager(ctx),
            event_manager=events,
        )

        state = await manager.ensure("atm-test")
        for _ in range(10):
            await manager.run_tick("atm-test")

        event_items = events.list_events("atm-test", limit=100)
        timeline_items = timeline.list_items("atm-test", limit=100)

        assert state.world.tick == 10
        assert state.world.day == 1
        assert len(event_items) == len(timeline_items)
        assert len(ctx.ws_handler.messages) == len(event_items)
        assert any(agent.memories for agent in state.agents.values())

        await manager.close()

    asyncio.run(scenario())
