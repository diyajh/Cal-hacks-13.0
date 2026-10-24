"""Explainable, deterministic match scoring (contract §13).

Item score  = 0.30 style + 0.20 color + 0.35 occasion + 0.15 preference   (each 0-100)
Outfit score = 0.30 style + 0.20 color + 0.20 occasion + 0.15 budget + 0.15 preference
Avoided colors/styles exclude an item entirely.
"""
from __future__ import annotations

from agents.core import taxonomy as tx

ITEM_WEIGHTS = {"style": 0.30, "color": 0.20, "occasion": 0.35, "preference": 0.15}
OUTFIT_WEIGHTS = {"style": 0.30, "color": 0.20, "occasion": 0.20, "budget": 0.15, "preference": 0.15}


def build_context(request: dict, profile: dict | None, occasion: str | None,
                  style_modifiers: list[str] | None = None) -> dict:
    profile = profile or {}
    avoid = set(request.get("avoid") or []) | set(profile.get("avoided_colors") or []) | set(profile.get("avoided_styles") or [])
    return {
        "styles": list(request.get("styles") or []) or list(profile.get("preferred_styles") or []),
        "preferred_colors": list(request.get("preferred_colors") or []) or list(profile.get("preferred_colors") or []),
        "avoid": sorted(avoid),
        "occasion": occasion,
        "preference_tags": sorted(set(profile.get("preference_tags") or []) | set(request.get("additional_preferences") or [])
                                  | set(profile.get("preferred_styles") or [])),
        "style_modifiers": list(style_modifiers or []),
    }


def _hits(terms: set[str], text: str) -> int:
    return sum(1 for t in terms if tx.term_in_text(t, text))


def avoid_reason(item: dict, avoid: list[str]) -> str | None:
    text = tx.product_text(item)
    colors = set(item.get("colors") or [])
    for a in avoid:
        group = tx.COLOR_GROUPS.get(a, {a})
        if colors & group or any(tx.term_in_text(g, text) for g in group):
            return a
    return None


def score_item(item: dict, ctx: dict) -> dict:
    """Score a Product or WardrobeItem for a context. Returns breakdown + total + excluded."""
    text = tx.product_text(item)
    reason = avoid_reason(item, ctx["avoid"])
    if reason:
        return {"score": 0, "style": 0, "color": 0, "occasion": 0, "preference": 0,
                "excluded": True, "reason": f"contains avoided '{reason}'"}

    style_terms = tx.expand_styles(ctx["styles"])
    style = 75.0
    if style_terms:
        style = 50 + min(50, _hits(style_terms, text) * 15)
    mod_score = None
    if ctx["style_modifiers"]:
        mod_hits = _hits(tx.expand_styles(ctx["style_modifiers"]), text)
        mod_score = 30 + min(70, mod_hits * 20)
        style = style * 0.4 + mod_score * 0.6

    colors = set(item.get("colors") or [])
    prefs = tx.expand_colors(ctx["preferred_colors"])
    if not prefs:
        color = 75.0
    elif colors & prefs:
        color = 100.0
    elif not colors:
        color = 65.0
    elif colors <= tx.NEUTRALS:
        color = 80.0
    else:
        color = 50.0

    occ = ctx["occasion"]
    if occ:
        occ_terms = set(tx.OCCASIONS.get(occ, [occ]))
        occasion = 55 + min(45, _hits(occ_terms, text) * 15)
    else:
        occasion = 75.0

    pref_terms = set(ctx["preference_tags"])
    preference = 70 + min(30, _hits(pref_terms, text) * 15) if pref_terms else 75.0

    total = (ITEM_WEIGHTS["style"] * style + ITEM_WEIGHTS["color"] * color
             + ITEM_WEIGHTS["occasion"] * occasion + ITEM_WEIGHTS["preference"] * preference)
    if mod_score is not None:  # an explicit "make it more X" request dominates the ranking
        total = total * 0.5 + mod_score * 0.5
    return {"score": round(total, 1), "style": round(style), "color": round(color),
            "occasion": round(occasion), "preference": round(preference), "excluded": False, "reason": None}


def score_outfit(item_scores: list[dict], items: list[dict], cost: float, per_outfit_budget: float | None) -> tuple[int, dict]:
    """Aggregate item scores into the contract's match_score + score_breakdown."""
    if not item_scores:
        return 1, {"style": 0, "color": 0, "occasion": 0, "budget": 0, "preference": 0}

    def avg(k):
        return sum(s[k] for s in item_scores) / len(item_scores)

    # compatibility: more than two distinct non-neutral colors clash
    loud = {c for it in items for c in (it.get("colors") or []) if c not in tx.NEUTRALS}
    color = avg("color") - (10 * (len(loud) - 2) if len(loud) > 2 else 0)

    if per_outfit_budget is None or cost <= per_outfit_budget:
        budget = 100.0
    else:
        budget = max(0.0, 100 - (cost - per_outfit_budget) / per_outfit_budget * 200)

    breakdown = {"style": round(avg("style")), "color": round(max(0, color)), "occasion": round(avg("occasion")),
                 "budget": round(budget), "preference": round(avg("preference"))}
    total = sum(OUTFIT_WEIGHTS[k] * breakdown[k] for k in OUTFIT_WEIGHTS)
    return max(1, min(100, round(total))), breakdown
