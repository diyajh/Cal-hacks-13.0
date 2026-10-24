import json
from pathlib import Path
from fastapi import APIRouter

from app.models.product import Product, ProductSearchRequest
from app.services.apify import search_apify

router = APIRouter(prefix="/products")

DATA = Path(__file__).parents[2] / "fallback_data/products.json"


@router.post("/search", response_model=list[Product])
async def search_products(req: ProductSearchRequest):
    try:
        products = await search_apify(
            req.query,
            req.max_price,
            req.limit
        )

        if products:
            return products

    except Exception as e:
        print("Apify failed:", e)

    # fallback
    products = json.loads(DATA.read_text())

    return [
        p for p in products
        if req.query.lower() in (
            p["name"] + " " +
            (p.get("description") or "") + " " +
            " ".join(p.get("tags", []))
        ).lower()
    ][:req.limit]