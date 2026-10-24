from datetime import datetime
from typing import List, Optional
from typing import Literal
from pydantic import BaseModel


class UserProfile(BaseModel):
    preferred_styles: List[str] = []
    preferred_colors: List[str] = []
    avoided_styles: List[str] = []
    avoided_colors: List[str] = []
    typical_budget: Optional[float] = None
    preference_tags: List[str] = []


class WardrobeItem(BaseModel):
    id: Optional[str] = None
    name: str
    category: Optional[str] = None
    colors: List[str] = []
    tags: List[str] = []
    memory_type: Literal["temporary", "remembered"] = "temporary"
    expires_at: Optional[datetime] = None
