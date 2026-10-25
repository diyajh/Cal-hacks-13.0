from typing import Any, Optional
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.vision import VisionAnalysisError, VisionNotConfiguredError, analyze_wardrobe_image
from app.services.wardrobe_decision import compare_product

router = APIRouter(prefix="/wardrobe")
log = logging.getLogger("aura.vision")


class DecisionRequest(BaseModel):
    product: dict[str, Any]
    wardrobe: list[dict[str, Any]] = Field(default_factory=list)
    budget_remaining: Optional[float] = None


@router.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload an image file")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="The wardrobe image is empty")
    try:
        return {"items": analyze_wardrobe_image(content, file.content_type), "provider": "configured_vision"}
    except VisionNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except VisionAnalysisError as exc:
        log.exception("wardrobe analysis failed filename=%s content_type=%s", file.filename, file.content_type)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/decision")
async def decision(req: DecisionRequest):
    return compare_product(req.product, req.wardrobe, req.budget_remaining)
