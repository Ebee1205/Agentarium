from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from src.service.agent.agent_schema import AgentAction, AgentState

if TYPE_CHECKING:
    from src.service.terrarium.terrarium_schema import SimulationState


class BaseAgentActor(ABC):
    """Agent의 행동 결정 방식에 대한 공통 인터페이스."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    @abstractmethod
    async def decide(
        self,
        *,
        state: "SimulationState",
        actor: AgentState,
    ) -> AgentAction:
        raise NotImplementedError
