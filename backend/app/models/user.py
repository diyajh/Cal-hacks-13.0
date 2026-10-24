from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class UserProfile(BaseModel):
    preferred_styles: list[str] = []
    preferred_colors: list[str] = []
    avoided_styles: list[str] = []
    avoided_colors: list[str] = []
    typical_budget: float | None = None
    preference_tags: list[str] = []


class WardrobeItem(BaseModel):
    id: str | None = None
    name: str
    category: str | None = None
    colors: list[str] = []
    tags: list[str] = []
    memory_type: Literal["temporary", "remembered"] = "temporary"
    expires_at: datetime | None = None