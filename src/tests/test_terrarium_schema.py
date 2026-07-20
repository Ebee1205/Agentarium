from src.service.terrarium.agent_manager import AgentManager
from src.service.terrarium.terrarium_schema import AgentActionType


class DummyContext:
    cfg = type("Cfg", (), {"llm": None})()
    llm_manager = None
    log = None


def test_default_agents_are_created():
    manager = AgentManager(DummyContext())
    agents = manager.create_default_agents()
    assert set(agents) == {"mori", "dodo", "ruru"}
    assert all(agent.relationships for agent in agents.values())


def test_action_enum_contains_mvp_actions():
    assert {item.value for item in AgentActionType} == {
        "TALK",
        "MOVE",
        "OBSERVE",
        "USE_RESOURCE",
        "WAIT",
    }
