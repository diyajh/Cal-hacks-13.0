import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.user import WardrobeItem, UserProfile
from app.routes.users import profiles, wardrobes

router = APIRouter(prefix="/shopping")
AGENTS_URL = "http://localhost:8001"


class PlanRequest(BaseModel):
    raw_request: str
    user_id: str
    session_id: str


class ModifyRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    target_outfit_id: str | None = None


@router.post("/plan")
async def plan(req: PlanRequest):
    now = datetime.now(timezone.utc)

    active_wardrobe = [
        item for item in wardrobes.get(req.user_id, [])
        if item.expires_at is None or item.expires_at > now
    ]

    payload = {
        "raw_request": req.raw_request,
        "user_id": req.user_id,
        "session_id": req.session_id,
        "profile": (
            profiles[req.user_id].model_dump()
            if req.user_id in profiles else {}
        ),
        "wardrobe": [
            item.model_dump(mode="json")
            for item in active_wardrobe
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{AGENTS_URL}/plan",
                json=payload
            )
            response.raise_for_status()
            result = response.json()

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Agent service unavailable: {e}"
        )

    # Save wardrobe memory returned by agents
    for data in result.get("wardrobe_items_to_save", []):
        item = WardrobeItem(
            id=data.get("id"),
            name=data["name"],
            category=data.get("category"),
            colors=data.get("colors", []),
            tags=data.get("tags", []),
            memory_type=data.get("memory_type", "temporary"),
            expires_at=data.get("expires_at")
        )

        user_items = wardrobes.setdefault(req.user_id, [])

        # Prevent duplicate saved items
        if not any(existing.id == item.id for existing in user_items):
            user_items.append(item)

    # Save profile updates returned by agents
    updates = result.get("profile_updates")

    if updates:
        current = profiles.get(req.user_id, UserProfile())
        updated = current.model_dump()
        updated.update(updates)
        profiles[req.user_id] = UserProfile(**updated)

    return result


@router.post("/modify")
async def modify(req: ModifyRequest):
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{AGENTS_URL}/modify",
                json=req.model_dump()
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Agent service unavailable: {e}"
        )