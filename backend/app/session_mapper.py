from typing import Any


def _product(item: dict[str, Any]) -> dict[str, Any]:
    product = item.get("product") or {}
    wardrobe = item.get("wardrobe_item") or {}
    owned = item.get("source_type") == "wardrobe" or not item.get("purchase_required", True)
    return {
        "id": item.get("id") or product.get("id") or wardrobe.get("id"),
        "name": product.get("name") or wardrobe.get("name") or "Wardrobe item",
        "retailer": product.get("retailer") or "Your wardrobe",
        "price": float(product.get("price") or 0),
        "category": product.get("category") or wardrobe.get("category") or "accessory",
        "image": product.get("image_url") or wardrobe.get("image_url") or "",
        "link": product.get("product_url") or wardrobe.get("id") or "",
        "owned": owned,
        "match": 100 if owned else 0,
        "note": product.get("description"),
    }


def to_style_session(payload: dict[str, Any]) -> dict[str, Any]:
    recommendation = payload.get("final_recommendation") or payload
    parsed = recommendation.get("parsed_request") or {}
    outfits = []
    for outfit in recommendation.get("outfits") or []:
        breakdown = outfit.get("score_breakdown") or {}
        outfits.append({
            "id": outfit.get("id"),
            "day": outfit.get("day") or len(outfits) + 1,
            "title": outfit.get("title") or "Planned look",
            "setting": outfit.get("occasion") or "Trip",
            "score": outfit.get("match_score") or 0,
            "scoreBreakdown": {
                "style": breakdown.get("style", 0),
                "color": breakdown.get("color", 0),
                "occasion": breakdown.get("occasion", 0),
                "budget": breakdown.get("budget", 0),
                "preference": breakdown.get("preference", 0),
            },
            "products": [_product(item) for item in outfit.get("items") or []],
            "newSpend": outfit.get("new_purchase_cost") or 0,
            "whyItWorks": outfit.get("why_it_works") or "",
            "accent": "#d88f68",
        })

    events = []
    for event in recommendation.get("agent_events") or []:
        events.append({
            "id": event.get("id"),
            "agent": event.get("agent", "orchestrator"),
            "title": event.get("type", "agent_event").replace("_", " ").title(),
            "detail": event.get("message", ""),
            "status": "done" if event.get("status") == "completed" else "active",
        })

    owned = [_product(item) for item in recommendation.get("owned_items_used") or []]
    reused = [_product(item) for item in recommendation.get("reused_items") or []]
    location = parsed.get("location") or "Your trip"
    days = parsed.get("duration_days") or parsed.get("number_of_outfits") or len(outfits)
    return {
        "session": recommendation.get("session_id"),
        "parsedRequest": {
            "destination": location,
            "dates": f"{days} days",
            "days": days,
            "aesthetic": ", ".join(parsed.get("styles") or []),
            "outfits": parsed.get("number_of_outfits") or len(outfits),
            "perOutfitBudget": parsed.get("per_outfit_budget") or 0,
            "totalBudget": parsed.get("total_budget") or 0,
            "required": [item.get("item", "") for item in parsed.get("required_items") or []],
            "avoid": parsed.get("avoid") or [],
            "owned": parsed.get("owned_item_references") or [],
        },
        "styleDNA": [],
        "outfits": outfits,
        "totalCost": recommendation.get("total_new_purchase_cost") or 0,
        "newPurchaseCost": recommendation.get("total_new_purchase_cost") or 0,
        "ownedItems": owned,
        "reusedItems": reused,
        "agentEvents": events,
        "constraintStatus": "satisfied" if recommendation.get("all_constraints_satisfied") else "conflict",
    }

