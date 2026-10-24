import os
import re
import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR = "JWEHgf5HWeoLlbchr"


def price_to_float(price):
    if not price:
        return None

    match = re.search(r"[\d,.]+", str(price))
    return float(match.group().replace(",", "")) if match else None


async def search_apify(query, category=None, max_price=None, limit=10):
    url = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"

    data = {
        "searchQuery": query,
        "country": "us",
        "language": "en",
        "limit": max(10, limit),
        "sortBy": "BEST_MATCH"
    }

    if max_price is not None:
        data["maxPrice"] = max_price

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=data
        )

        response.raise_for_status()
        items = response.json()

    products = []

    for item in items[:limit]:
        price = price_to_float(item.get("price"))

        if price is None:
            continue

        photos = item.get("product_photos") or []

        products.append({
            "id": item.get("product_id") or str(len(products)),
            "name": item.get("product_title") or "Unknown Product",
            "category": category,
            "price": price,
            "currency": "USD",
            "retailer": item.get("store_name") or "Unknown",
            "image_url": photos[0] if photos else None,
            "product_url": item.get("product_page_url"),
            "description": None,
            "colors": [],
            "tags": [],
            "available": True,
            "source": "apify"
        })

    return products