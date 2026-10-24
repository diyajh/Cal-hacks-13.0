import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.routes.users import profiles, wardrobes
from app.config import load_settings

router = APIRouter(prefix="/shopping")
AGENTS_URL = load_settings().agents_base_url


class PlanRequest(BaseModel):
    raw_request: str
    user_id: str
    session_id: str


class ModifyRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    target_outfit_id: Optional[str] = None


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
            if req.user_id in profiles
            else {}
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
            return response.json()

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Agent service unavailable: {e}"
        )


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
