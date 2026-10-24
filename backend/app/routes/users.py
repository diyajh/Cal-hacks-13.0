from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from app.models.user import UserProfile, WardrobeItem

router = APIRouter(prefix="/users")

profiles = {}
wardrobes = {}


@router.put("/{user_id}/profile")
def save_profile(user_id: str, profile: UserProfile):
    profiles[user_id] = profile
    return profile


@router.get("/{user_id}/profile")
def get_profile(user_id: str):
    return profiles.get(user_id, UserProfile())


@router.post("/{user_id}/wardrobe")
def add_item(user_id: str, item: WardrobeItem):
    item.id = str(uuid4())

    if item.memory_type == "temporary":
        item.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        item.expires_at = None

    wardrobes.setdefault(user_id, []).append(item)

    return item


@router.get("/{user_id}/wardrobe")
def get_wardrobe(user_id: str):
    now = datetime.now(timezone.utc)

    items = [
        item
        for item in wardrobes.get(user_id, [])
        if item.expires_at is None or item.expires_at > now
    ]

    wardrobes[user_id] = items

    return items


@router.delete("/{user_id}/wardrobe/{item_id}")
def delete_item(user_id: str, item_id: str):
    items = wardrobes.get(user_id, [])

    for item in items:
        if item.id == item_id:
            items.remove(item)
            return {"deleted": True}

    raise HTTPException(status_code=404, detail="Wardrobe item not found")