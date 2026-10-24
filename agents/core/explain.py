"""'Why this works' text built only from real facts (product fields, request, costs).
Deterministic so it can never hallucinate prices or product details."""
from __future__ import annotations

from agents.core import taxonomy as tx


def _usd(x: float) -> str:
    return f"${x:,.2f}"


def _join(xs: list[str]) -> str:
    xs = [x for x in xs if x]
    if len(xs) <= 1:
        return "".join(xs)
    return ", ".join(xs[:-1]) + " and " + xs[-1]


def why_it_works(outfit: dict, request: dict, required_kinds: list[str] | None = None) -> str:
    items = outfit["items"]
    if not items:
        return "I couldn't complete this outfit with the products available."
    datas = [(i["product"] or i["wardrobe_item"]) for i in items]
    text = " ".join(tx.product_text(d) for d in datas)

    sentences = []
    styles = request.get("styles") or []
    style_hits = sorted({t for t in tx.expand_styles(styles) if tx.term_in_text(t, text)})
    colors = sorted({c for d in datas for c in d.get("colors") or []})
    pref = tx.expand_colors(request.get("preferred_colors") or [])
    palette = [c for c in colors if c in pref]

    lead = f"Built for {outfit['occasion']}"
    if styles:
        lead += f" with the {_join(styles[:2])} look you asked for"
    if style_hits:
        lead += f" — {_join(style_hits[:3])} details carry the vibe"
    sentences.append(lead + ".")
    if palette:
        sentences.append(f"It stays in your {_join(palette[:3])} palette.")

    req_hits = [k for k in (required_kinds or []) if any(tx.matches_kind(d, k) for d in datas)]
    if req_hits:
        sentences.append(f"Includes your requested {_join(req_hits)}.")

    owned = [i["wardrobe_item"]["name"] for i in items if i["source_type"] == "wardrobe"]
    if owned:
        sentences.append(f"Your own {_join(owned)} complete{'s' if len(owned) == 1 else ''} it at no extra cost.")
    reused = [i["product"]["name"] for i in items if i["source_type"] == "product" and i["reused"]]
    if reused:
        sentences.append(f"{_join(reused)} {'is' if len(reused) == 1 else 'are'} reused in other outfits, so you only buy "
                         f"{'it' if len(reused) == 1 else 'them'} once.")
    limit = request.get("per_outfit_budget")
    cost = outfit["new_purchase_cost"]
    if limit is not None:
        sentences.append(f"New purchases: {_usd(cost)} of your {_usd(limit)} per-outfit budget.")
    else:
        sentences.append(f"New purchases: {_usd(cost)}.")
    return " ".join(sentences)
