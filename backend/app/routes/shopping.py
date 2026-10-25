import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from app.routes import users
from app.models.user import UserProfile
from app.config import load_settings
from app.services.wardrobe_decision import compare_product

router = APIRouter(prefix="/shopping")
AGENTS_URL = load_settings().agents_base_url
log = logging.getLogger("aura.shopping")


class DecisionRequest(BaseModel):
    product: dict
    wardrobe: list[dict] = []
    budget_remaining: Optional[float] = None
    per_outfit_budget: Optional[float] = None
    total_budget: Optional[float] = None
    spent_total: Optional[float] = None


@router.post("/decision")
async def decision(req: DecisionRequest):
    result = compare_product(req.product, req.wardrobe, req.budget_remaining)
    price = req.product.get("price")
    if price is not None and req.per_outfit_budget is not None and float(price) > req.per_outfit_budget:
        result.update(verdict="SKIP", budget_impact=float(price),
                      reason=f"This item costs ${float(price):.2f}, over this outfit's ${req.per_outfit_budget:.2f} budget.")
    elif price is not None and req.total_budget is not None and req.spent_total is not None:
        remaining = max(req.total_budget - req.spent_total, 0)
        if float(price) > remaining:
            result.update(verdict="SKIP", budget_impact=float(price),
                          reason=f"This item would exceed the remaining ${remaining:.2f} trip allocation.")
    return result


class PlanRequest(BaseModel):
    raw_request: str
    user_id: str
    session_id: str
    wardrobe: list[dict] = []
    profile: Optional[UserProfile] = None


class ModifyRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    target_outfit_id: Optional[str] = None
    wardrobe: list[dict] = []
    profile: Optional[UserProfile] = None


@router.post("/plan")
async def plan(req: PlanRequest):
    stored_wardrobe = users.wardrobe_store.list(req.user_id)
    seen = {item.id for item in stored_wardrobe if item.id}
    request_wardrobe = [item for item in req.wardrobe if item.get("id") not in seen]
    log.info("plan request inventory count=%d ids=%s categories=%s sources=%s", len(stored_wardrobe) + len(request_wardrobe),
             [item.id for item in stored_wardrobe] + [item.get("id") for item in request_wardrobe],
             [item.category for item in stored_wardrobe] + [item.get("category") for item in request_wardrobe],
             ["wardrobe"] * len(stored_wardrobe) + [item.get("source", "wardrobe") for item in request_wardrobe])

    payload = {
        "raw_request": req.raw_request,
        "user_id": req.user_id,
        "session_id": req.session_id,
        "profile": (req.profile or users.wardrobe_store.get_profile(req.user_id)).model_dump(mode="json"),
        "wardrobe": [
            *[item.model_dump(mode="json") for item in stored_wardrobe],
            *request_wardrobe,
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
    stored_profile = req.profile or users.wardrobe_store.get_profile(req.user_id)
    payload = req.model_dump(mode="json")
    payload["profile"] = stored_profile.model_dump(mode="json")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{AGENTS_URL}/modify",
                json=payload
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Agent service unavailable: {e}"
        )
