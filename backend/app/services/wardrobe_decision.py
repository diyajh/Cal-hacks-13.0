"""Deterministic product-vs-wardrobe comparison.

Duplicate detection deliberately runs before outfit-value heuristics. Vision and
product metadata can be incomplete, so uncertain footwear never receives a
confident BUY decision.
"""
from __future__ import annotations

from typing import Any, Optional

FOOTWEAR_CATEGORIES = {"shoe", "shoes", "sneaker", "sneakers", "footwear", "sandal", "sandals", "boot", "boots", "heel", "heels"}
FOOTWEAR_SUBTYPES = {
    "sneaker": {"sneaker", "sneakers", "trainer", "trainers", "running", "runner", "runners", "athletic", "court", "tennis", "low top", "high top"},
    "sandal": {"sandal", "sandals", "slide", "slides", "flip flop", "flip flops", "espadrille", "espadrilles"},
    "boot": {"boot", "boots", "ankle boot", "hiking", "combat"},
    "heel": {"heel", "heels", "pump", "pumps", "stiletto", "platform"},
}

def _words(value: Any) -> set[str]:
    return {word for word in str(value or "").lower().replace("-", " ").split() if len(word) > 2}

def _category(value: Any) -> str:
    raw = str(value or "").lower().replace("-", " ").strip()
    if raw in FOOTWEAR_CATEGORIES:
        return "shoes"
    if raw in {"bottom", "pants", "trouser", "trousers"}:
        return "pants"
    if raw in {"top", "shirt", "blouse", "tee", "t shirt"}:
        return "top"
    if raw in {"jacket", "coat", "outerwear", "overshirt"}:
        return "outerwear"
    return raw

def _subtype(value: Any, item: dict[str, Any]) -> Optional[str]:
    raw = str(value or "").lower().replace("-", " ").replace("_", " ").strip()
    vocabulary = _words(" ".join(str(item.get(key) or "") for key in ("name", "description", "category", "subcategory", "subtype", "style")))
    if raw and raw not in {"unknown", "other", "shoe", "shoes", "footwear"}:
        for subtype, terms in FOOTWEAR_SUBTYPES.items():
            if raw in terms or raw == subtype or _words(raw) & terms:
                return subtype
        return raw
    for subtype, terms in FOOTWEAR_SUBTYPES.items():
        if vocabulary & terms:
            return subtype
    return None

def _color(value: Any) -> Optional[str]:
    colors = str(value or "").lower().replace("/", " ").split()
    colors = [color for color in colors if color not in {"and", "with"}]
    return colors[0] if colors else None

def _features(item: dict[str, Any]) -> tuple[str, Optional[str], Optional[str]]:
    category = _category(item.get("category"))
    subtype = _subtype(item.get("subtype") or item.get("subcategory"), item)
    color = _color(item.get("color") or (item.get("colors") or [None])[0])
    return category, subtype, color

def _result(verdict: str, confidence: float, duplication: float, unlocked: int,
            impact: Optional[float], reason: str, matched: list[dict[str, Any]],
            missing: list[str]) -> dict[str, Any]:
    return {"verdict": verdict, "confidence": round(confidence, 2),
            "duplication_score": round(duplication, 2), "outfits_unlocked": unlocked,
            "budget_impact": impact, "reason": reason,
            "matched_items": matched, "missing_information": missing}

def compare_product(product: dict[str, Any], wardrobe: list[dict[str, Any]], budget_remaining: Optional[float] = None) -> dict[str, Any]:
    price = _price(product)
    if not wardrobe:
        return _result("INSUFFICIENT_WARDROBE_DATA", 0.0, 0.0, 0, price, "Add your wardrobe to analyze duplication.", [], ["wardrobe photo"])
    if price is None:
        return _result("INSUFFICIENT_WARDROBE_DATA", 0.0, 0.0, 0, None, "Aura found the wardrobe, but the active product has no reliable price.", [], ["product price"])
    low_confidence = [item for item in wardrobe if float(item.get("confidence", 0) or 0) < 0.65]
    if low_confidence:
        return _result("INSUFFICIENT_WARDROBE_DATA", 0.42, 0.0, 0, price, "Some wardrobe items need your confirmation before Aura can judge duplication.", [], ["confirm low-confidence wardrobe items"])

    product_category, product_subtype, product_color = _features(product)
    matches: list[tuple[float, dict[str, Any]]] = []
    uncertain = False
    for item in wardrobe:
        item_category, item_subtype, item_color = _features(item)
        if product_category != item_category:
            continue
        if product_category == "shoes" and (not product_subtype or not item_subtype):
            uncertain = True
            continue
        score = 0.35
        if product_subtype and item_subtype and product_subtype == item_subtype:
            score += 0.35
        elif product_subtype and item_subtype:
            score -= 0.15
        else:
            uncertain = True
        if product_color and item_color and product_color == item_color:
            score += 0.30
        elif product_color and item_color:
            score -= 0.10
        else:
            uncertain = True
        matches.append((max(0.0, min(score, 1.0)), item))

    matches.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best_item = matches[0] if matches else (0.0, None)
    if best_item and best_score >= 0.8:
        item_category, item_subtype, item_color = _features(best_item)
        label = f"{item_color or ''} {item_subtype or item_category}".strip()
        return _result("SKIP", min(0.98, 0.7 + best_score * 0.25), best_score, 0, price, f"Duplicates your {label}. ${price:.2f} avoided.", [best_item], [])
    if uncertain and product_category == "shoes":
        return _result("INSUFFICIENT_WARDROBE_DATA", 0.42, best_score, 0, price, "Confirm the footwear subtype before Aura decides whether this adds coverage.", [best_item] if best_item else [], ["confirm footwear subtype"])
    if budget_remaining is not None and price > budget_remaining:
        return _result("SKIP", min(0.94, 0.7 + best_score * 0.2), best_score, 0, price, f"This product costs ${price:.2f}, which is ${price - budget_remaining:.2f} over your remaining budget.", [item for _, item in matches], [])
    compatible_count = sum(1 for item in wardrobe if _category(item.get("category")) not in {product_category, ""})
    unlocked = max(1, min(5, compatible_count))
    category_label = product_subtype or product_category or "item"
    return _result("BUY", min(0.92, 0.62 + (1 - best_score) * 0.25), best_score, unlocked, price, f"This {category_label} adds new coverage and can create {unlocked} new combination{'s' if unlocked != 1 else ''}.", [item for _, item in matches], [])

def _price(product: dict[str, Any]) -> Optional[float]:
    value = product.get("price")
    try:
        return round(float(value), 2) if value is not None and str(value) != "" else None
    except (TypeError, ValueError):
        return None
