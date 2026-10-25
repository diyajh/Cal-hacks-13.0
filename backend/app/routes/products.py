import os
from fastapi import APIRouter, HTTPException

from app.models.product import Product, ProductSearchRequest
from app.services.apify import search_apify

router = APIRouter(prefix="/products")

@router.post("/search", response_model=list[Product])
async def search_products(req: ProductSearchRequest):
    if not os.getenv("APIFY_API_TOKEN", "").strip():
        raise HTTPException(status_code=503, detail="LIVE SEARCH NOT CONFIGURED — set APIFY_API_TOKEN in backend/.env")
    try:
        products = await search_apify(
            req.query,
            req.category,
            req.max_price,
            req.limit
        )

        if products:
            return products

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LIVE SEARCH FAILED — {e}") from e

    raise HTTPException(status_code=404, detail="LIVE SEARCH RETURNED NO PRODUCTS")
