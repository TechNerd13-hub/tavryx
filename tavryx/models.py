from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

class Mode(str, Enum):
    INCIDENT = "INCIDENT"
    DECISION = "DECISION"
    LEARNING = "LEARNING"
    CREATIVE = "CREATIVE"
    PLANNING = "PLANNING"
    GENERAL = "GENERAL"

class Lifecycle(str, Enum):
    EMERGING = "EMERGING"
    ACTIVE = "ACTIVE"
    ESCALATING = "ESCALATING"
    BLOCKED = "BLOCKED"
    RESOLVING = "RESOLVING"
    RESOLVED = "RESOLVED"
    PARKED = "PARKED"

class Situation(BaseModel):
    situation_id: str = ""
    title: str = "Untitled situation"
    mode: Mode = Mode.GENERAL
    lifecycle: Lifecycle = Lifecycle.EMERGING
    severity: str = "LOW"
    trajectory: str = "EMERGING"
    confidence: int = Field(default=70, ge=0, le=100)
    reasoning_level: str = "FAST"
    summary: str = ""
    answer: str = ""
    impact: str = ""
    evidence: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    recommendation: str = ""
    next_move: str = ""
    why: str = ""
    state_delta: str = ""
    decision_revised: bool = False
    revision_reason: str = ""
    observed: list[str] = Field(default_factory=list)
    inferred: list[str] = Field(default_factory=list)
    recommended: list[str] = Field(default_factory=list)
    executed: list[str] = Field(default_factory=list)
    verified: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_ms: int | None = None


class IncomingMessage(BaseModel):
    text: str
    sender: str = "unknown"
    channel: str = "api"
    message_id: str | None = None
    mode: str | None = None

class AgentResult(BaseModel):
    situation: Situation
    response: str
