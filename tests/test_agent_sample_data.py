from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.service.agent.agent_schema import AgentState


SAMPLE_DATA_PATH = REPO_ROOT / "src/service/data/actor-sample-data.json"


def _validate_agent(data: dict) -> None:
    if hasattr(AgentState, "model_validate"):
        AgentState.model_validate(data)
    else:
        AgentState.parse_obj(data)


def _build_agent(data: dict) -> AgentState:
    if hasattr(AgentState, "model_validate"):
        return AgentState.model_validate(data)
    return AgentState.parse_obj(data)


def test_actor_sample_data_matches_agent_schema() -> None:
    raw_agents = json.loads(SAMPLE_DATA_PATH.read_text(encoding="utf-8"))

    assert isinstance(raw_agents, list), (
        "actor-sample-data.json 최상위 값은 list여야 합니다."
    )
    assert raw_agents, "actor-sample-data.json이 비어 있습니다."

    for index, agent_data in enumerate(raw_agents):
        assert isinstance(agent_data, dict), (
            f"Agent sample index={index} 항목은 object여야 합니다."
        )

        normalized = dict(agent_data)
        if "location_id" not in normalized and "initial_location" in normalized:
            normalized["location_id"] = normalized.pop("initial_location")

        agent_id = normalized.get("agent_id", f"index={index}")
        try:
            _validate_agent(normalized)
        except Exception as exc:
            raise AssertionError(
                f"Agent sample data 검증 실패: agent_id={agent_id}: {exc}"
            ) from exc

        if "speech_rule" in normalized and "forbidden_phrases" in normalized["speech_rule"]:
            agent = _build_agent(normalized)
            assert agent.speech_rule.forbidden_phrases == normalized["speech_rule"]["forbidden_phrases"], (
                f"Agent sample data forbidden_phrases 매핑 실패: agent_id={agent_id}"
            )
