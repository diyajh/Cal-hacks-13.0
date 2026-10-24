"""Builders/normalizers for the shared JSON contract (shared/CONTRACT.md).

Everything here produces plain dicts that match the contract exactly:
unknown scalars -> None, empty lists -> [], money -> float USD, ids -> str,
dates -> ISO-8601 'Z' strings, snake_case keys.
"""
from __future__ import annotations

import datetime as _dt
import re
import uuid
from typing import Any

CURRENCY = "USD"
EVENT_STATUSES = {"working", "completed", "failed"}
REC_STATUSES = {"processing", "completed", "needs_user_input", "failed"}
CATEGORIES = {"top", "bottom", "dress", "shoes", "outerwear", "accessory"}

_CATEGORY_ALIASES = {
    "top": "top", "tops": "top", "shirt": "top", "shirts": "top", "blouse": "top",
    "tee": "top", "t-shirt": "top", "tank": "top", "sweater": "top",
    "bottom": "bottom", "bottoms": "bottom", "skirt": "bottom", "skirts": "bottom",
    "pants": "bottom", "shorts": "bottom", "jeans": "bottom", "trousers": "bottom",
    "dress": "dress", "dresses": "dress", "romper": "dress", "jumpsuit": "dress",
    "shoes": "shoes", "shoe": "shoes", "footwear": "shoes", "sneakers": "shoes",
    "sandals": "shoes", "heels": "shoes", "boots": "shoes",
    "outerwear": "outerwear", "jacket": "outerwear", "jackets": "outerwear",
    "coat": "outerwear", "blazer": "outerwear", "cardigan": "outerwear",
    "accessory": "accessory", "accessories": "accessory", "bag": "accessory",
    "hat": "accessory", "jewelry": "accessory", "sunglasses": "accessory",
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def money(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        m = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
        return round(float(m.group()), 2) if m else None
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    out: list[str] = []
    for v in value:
        if isinstance(v, str) and v.strip() and v.strip().lower() not in out:
            out.append(v.strip().lower())
    return out


def normalize_category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _CATEGORY_ALIASES.get(value.strip().lower())


# --------------------------------------------------------------------------- ShoppingRequest

SHOPPING_REQUEST_KEYS = [
    "session_id", "user_id", "raw_request", "location", "duration_days", "number_of_outfits",
    "occasions", "styles", "preferred_colors", "avoid", "required_items", "per_outfit_budget",
    "total_budget", "currency", "owned_item_references", "additional_preferences",
    "hard_constraints", "soft_preferences",
]


def normalize_shopping_request(data: dict, session_id: str, user_id: str, raw_request: str) -> dict:
    """Coerce any (LLM or rule) output into a contract-valid ShoppingRequest."""
    data = data or {}
    req_items = []
    for it in data.get("required_items") or []:
        if isinstance(it, str):
            it = {"item": it}
        if not isinstance(it, dict) or not isinstance(it.get("item"), str) or not it["item"].strip():
            continue
        target = it.get("required_for_outfit")
        if isinstance(target, int):
            target = f"outfit_{target}"
        req_items.append({
            "item": it["item"].strip().lower(),
            "quantity": max(1, _int_or_none(it.get("quantity")) or 1),
            "required_for_outfit": target if isinstance(target, str) and target else None,
        })

    req = {
        "session_id": session_id,
        "user_id": user_id,
        "raw_request": raw_request,
        "location": data.get("location") if isinstance(data.get("location"), str) and data.get("location").strip() else None,
        "duration_days": _int_or_none(data.get("duration_days")),
        "number_of_outfits": _int_or_none(data.get("number_of_outfits")),
        "occasions": _str_list(data.get("occasions")),
        "styles": _str_list(data.get("styles")),
        "preferred_colors": _str_list(data.get("preferred_colors")),
        "avoid": _str_list(data.get("avoid")),
        "required_items": req_items,
        "per_outfit_budget": money(data.get("per_outfit_budget")),
        "total_budget": money(data.get("total_budget")),
        "currency": CURRENCY,
        "owned_item_references": [str(x) for x in (data.get("owned_item_references") or []) if x],
        "additional_preferences": _str_list(data.get("additional_preferences")),
        "hard_constraints": [],
        "soft_preferences": [],
    }
    if req["number_of_outfits"] is None and req["duration_days"]:
        req["number_of_outfits"] = req["duration_days"]
    req["hard_constraints"], req["soft_preferences"] = derive_constraint_lists(req, data)
    return req


def derive_constraint_lists(req: dict, data: dict | None = None) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    if req.get("per_outfit_budget") is not None:
        hard.append("per_outfit_budget")
    if req.get("total_budget") is not None:
        hard.append("total_budget")
    if req.get("number_of_outfits"):
        hard.append("number_of_outfits")
    if req.get("required_items"):
        hard.append("required_items")
    given_hard = _str_list((data or {}).get("hard_constraints"))
    if "avoid" in given_hard and req.get("avoid"):
        hard.append("avoid")
    soft = [k for k in ("styles", "preferred_colors", "occasions") if req.get(k)]
    return hard, soft


# --------------------------------------------------------------------------- Product / wardrobe

def normalize_product(p: Any) -> dict | None:
    """Validate a Product coming from Person 2 / fallback. Returns None if unusable.
    Never invents data: missing optional fields become None / []."""
    if not isinstance(p, dict):
        return None
    price = money(p.get("price"))
    category = normalize_category(p.get("category"))
    if not p.get("id") or not p.get("name") or price is None or category is None:
        return None
    return {
        "id": str(p["id"]),
        "name": str(p["name"]),
        "category": category,
        "subcategory": p.get("subcategory") or None,
        "price": price,
        "currency": p.get("currency") or CURRENCY,
        "retailer": p.get("retailer") or None,
        "image_url": p.get("image_url") or None,
        "product_url": p.get("product_url") or None,
        "description": p.get("description") or None,
        "colors": _str_list(p.get("colors")),
        "tags": _str_list(p.get("tags")),
        "available": bool(p.get("available", True)),
        "source": p.get("source") or None,
        "source_id": str(p["source_id"]) if p.get("source_id") is not None else None,
    }


def wardrobe_item_active(item: dict, now: _dt.datetime | None = None) -> bool:
    """Temporary memory expires at expires_at (contract §9). Remembered never expires."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    exp = parse_iso(item.get("expires_at"))
    return exp is None or now < exp


def make_wardrobe_item(user_id: str, name: str, category: str | None, subcategory: str | None,
                       colors: list[str], tags: list[str], remembered: bool,
                       estimated_value: float | None = None, item_id: str | None = None) -> dict:
    created = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    expires = None if remembered else created + _dt.timedelta(days=30)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return {
        "id": item_id or f"wardrobe_{slug}",
        "user_id": user_id,
        "name": name.title(),
        "category": category,
        "subcategory": subcategory,
        "colors": colors,
        "tags": tags,
        "image_url": None,
        "estimated_value": estimated_value,
        "memory_type": "remembered" if remembered else "temporary",
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z") if expires else None,
    }


# --------------------------------------------------------------------------- events / violations

def make_event(session_id: str, agent: str, type_: str, message: str,
               status: str = "completed", outfit_id: str | None = None) -> dict:
    assert status in EVENT_STATUSES
    return {
        "id": new_id("event"),
        "session_id": session_id,
        "agent": agent,
        "type": type_,
        "status": status,
        "message": message,
        "outfit_id": outfit_id,
        "timestamp": now_iso(),
    }


def make_violation(constraint: str, expected: Any, actual: Any, outfit_id: str | None,
                   message: str, severity: str = "hard", resolution: str = "replan") -> dict:
    return {
        "id": new_id("violation"),
        "constraint": constraint,
        "expected": expected,
        "actual": actual,
        "outfit_id": outfit_id,
        "severity": severity,
        "resolution": resolution,
        "message": message,
    }


def empty_final_recommendation(session_id: str, status: str, message: str,
                               parsed_request: dict | None = None,
                               events: list | None = None) -> dict:
    assert status in REC_STATUSES
    return {
        "session_id": session_id,
        "status": status,
        "parsed_request": parsed_request or {},
        "outfits": [],
        "total_new_purchase_cost": 0.0,
        "total_budget": (parsed_request or {}).get("total_budget"),
        "owned_items_used": [],
        "reused_items": [],
        "agent_events": events or [],
        "constraint_violations": [],
        "all_constraints_satisfied": False,
        "message": message,
    }
