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
    subcategory: Optional[str] = None
    subtype: Optional[str] = None
    color: Optional[str] = None
    material: Optional[str] = None
    pattern: Optional[str] = None
    style: Optional[str] = None
    formality: Optional[str] = None
    confidence: Optional[float] = None
    image_url: Optional[str] = None
    source: Literal["wardrobe"] = "wardrobe"
    memory_type: Literal["temporary", "remembered"] = "temporary"
    expires_at: Optional[datetime] = None
