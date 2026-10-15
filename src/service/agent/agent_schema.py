from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, Field


class AgentActionType(str, Enum):
    TALK = "TALK"
    MOVE = "MOVE"
    OBSERVE = "OBSERVE"
    USE_RESOURCE = "USE_RESOURCE"
    WAIT = "WAIT"


class SpeechTone(str, Enum):
    NEUTRAL = "neutral"
    CALM = "calm"
    WARM = "warm"
    BLUNT = "blunt"
    GUARDED = "guarded"
    PERSUASIVE = "persuasive"
    ANALYTICAL = "analytical"
    AUTHORITATIVE = "authoritative"
    SARCASTIC = "sarcastic"
    SUSPICIOUS = "suspicious"
    PROVOCATIVE = "provocative"
    AGGRESSIVE = "aggressive"
    ARROGANT = "arrogant"


class SpeechLevel(str, Enum):
    CASUAL = "casual"
    NEUTRAL = "neutral"
    POLITE = "polite"
    FORMAL = "formal"
    INFORMAL = "informal"

class SentenceLength(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class ConflictStyle(str, Enum):
    AVOID = "avoid"
    NEGOTIATE = "negotiate"
    CONFRONT = "confront"
    MANIPULATE = "manipulate"
    CONTROL = "control"
    ATTACK = "attack"


class DecisionStyle(str, Enum):
    IMPULSIVE = "impulsive"
    BALANCED = "balanced"
    DELIBERATE = "deliberate"
    OPPORTUNISTIC = "opportunistic"


class SpeechRule(BaseModel):
    """Agent가 대사를 표현하는 방식을 규격화한다."""

    tones: list[SpeechTone] = Field(
        default_factory=lambda: [SpeechTone.NEUTRAL]
    )
    speech_level: SpeechLevel = SpeechLevel.NEUTRAL
    sentence_length: SentenceLength = SentenceLength.MEDIUM
    max_sentences: int = Field(default=2, ge=1, le=3)
    max_chars: int = Field(default=160, ge=20, le=300)
    directness: int = Field(default=50, ge=0, le=100)
    emotional_expression: int = Field(default=50, ge=0, le=100)
    question_tendency: int = Field(default=50, ge=0, le=100)
    address_style: str = "상황에 맞게 상대를 부른다."
    verbal_habits: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "forbidden_phrases",
            "forbidden_behaviors",
        ),
    )


class ActRule(BaseModel):
    """Agent가 행동을 선택하고 갈등에 대응하는 방식을 규격화한다."""

    initiative: int = Field(default=50, ge=0, le=100)
    risk_tolerance: int = Field(default=50, ge=0, le=100)
    cooperation: int = Field(default=50, ge=0, le=100)
    secrecy: int = Field(default=50, ge=0, le=100)
    conflict_style: ConflictStyle = ConflictStyle.NEGOTIATE
    decision_style: DecisionStyle = DecisionStyle.BALANCED
    action_bias: dict[str, int] = Field(
        default_factory=lambda: {
            AgentActionType.TALK.value: 0,
            AgentActionType.MOVE.value: 0,
            AgentActionType.OBSERVE.value: 0,
            AgentActionType.USE_RESOURCE.value: 0,
            AgentActionType.WAIT.value: 0,
        }
    )
    priorities: list[str] = Field(default_factory=list)
    conditional_rules: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    personality: dict[str, int] = Field(default_factory=dict)
    speech_rule: SpeechRule = Field(default_factory=SpeechRule)
    act_rule: ActRule = Field(default_factory=ActRule)
    needs: dict[str, int] = Field(
        default_factory=lambda: {
            "hunger": 20,
            "energy": 80,
            "loneliness": 20,
        }
    )
    location_id: str = "nest"
    current_emotion: str = "calm"
    relationships: dict[str, int] = Field(default_factory=dict)
    memories: list[str] = Field(default_factory=list)
    action_history: list[str] = Field(default_factory=list)
    dialogue_history: list[str] = Field(default_factory=list)
    goal: str = "오늘 하루를 무사히 보낸다."
    secret: str | None = None


class AgentAction(BaseModel):
    action: AgentActionType
    target_agent_id: str | None = None
    target_location_id: str | None = None
    resource: str | None = None

    narration: str = ""
    content: str | None = None
    emotion: str = "neutral"
    relationship_delta: int = Field(default=0, ge=-3, le=3)
    reason: str = ""

    # 서버 내부 메타데이터. LLM 응답 스키마에는 포함하지 않는다.
    source: str = Field(default="unknown", exclude=True)
    reply_content: str | None = Field(default=None, exclude=True)
    reply_narration: str | None = Field(default=None, exclude=True)
    reply_emotion: str | None = Field(default=None, exclude=True)
    reply_relationship_delta: int = Field(default=0, exclude=True)
    reply_reason: str | None = Field(default=None, exclude=True)
    reply_source: str | None = Field(default=None, exclude=True)


class AgentReply(BaseModel):
    narration: str = Field(min_length=1)
    content: str = Field(min_length=1)
    emotion: str = Field(min_length=1)
    relationship_delta: int = Field(default=0, ge=-3, le=3)
    reason: str = Field(min_length=1)


AGENT_ACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [item.value for item in AgentActionType],
        },
        "target_agent_id": {"type": ["string", "null"]},
        "target_location_id": {"type": ["string", "null"]},
        "resource": {"type": ["string", "null"]},
        "narration": {"type": "string"},
        "content": {"type": ["string", "null"]},
        "emotion": {"type": "string"},
        "relationship_delta": {
            "type": "integer",
            "minimum": -3,
            "maximum": 3,
        },
        "reason": {"type": "string"},
    },
    "required": [
        "action",
        "target_agent_id",
        "target_location_id",
        "resource",
        "narration",
        "content",
        "emotion",
        "relationship_delta",
        "reason",
    ],
    "additionalProperties": False,
}


AGENT_REPLY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "narration": {"type": "string"},
        "content": {"type": "string"},
        "emotion": {"type": "string"},
        "relationship_delta": {
            "type": "integer",
            "minimum": -3,
            "maximum": 3,
        },
        "reason": {"type": "string"},
    },
    "required": [
        "narration",
        "content",
        "emotion",
        "relationship_delta",
        "reason",
    ],
    "additionalProperties": False,
}
