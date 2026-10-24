from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    agent: str
    status: str
    message: str
    type: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VoiceTurnRequest(BaseModel):
    session_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1, max_length=4000)


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class VoiceTurnResponse(BaseModel):
    session_id: str
    transcript: str
    response_text: str
    audio_url: Optional[str] = None
    audio_data_url: Optional[str] = None
    agent_events: list[dict[str, object]] = Field(default_factory=list)
    style_session: Optional[dict[str, object]] = None
    provider: Literal["cartesia"]
    status: Literal["accepted", "completed"]


class TranscriptionResponse(BaseModel):
    session_id: str
    transcript: str
    provider: Literal["cartesia"]
    model: str

