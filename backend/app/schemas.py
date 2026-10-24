from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


AgentName = Literal["style", "search", "budget", "planner", "memory"]
AgentStatus = Literal["started", "progress", "success", "rejected", "error"]


class AgentEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    agent: AgentName
    status: AgentStatus
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VoiceTurnRequest(BaseModel):
    session_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1, max_length=4000)


class VoiceTurnResponse(BaseModel):
    session_id: str
    transcript: str
    response_text: str
    audio_url: Optional[str] = None
    agent_events: list[AgentEvent] = Field(default_factory=list)
    provider: Literal["cartesia"]
    status: Literal["accepted", "completed"]

