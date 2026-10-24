"""Natural language -> ShoppingRequest.

Strategy (contract §25 "LLM parsing fails"):
  1. LLM extraction (if a key is configured), retry once.
  2. Deterministic rule-based extraction always runs too; it fills any gaps the LLM
     left and is the full fallback when no LLM is available.
raw_request is always retained.
"""
from __future__ import annotations

import json
import re

from agents.core import taxonomy as tx
from agents.core.contract import make_wardrobe_item, normalize_shopping_request
from agents.core.llm import call_llm_json, llm_available

_NUM = r"\b(\d+|" + "|".join(sorted(tx.NUMBER_WORDS, key=len, reverse=True)) + r")"
_N = r"(\d+(?:,\d{3})*(?:\.\d+)?)"
# money with an explicit marker: $50, 50$, 50 dollars/usd/bucks
_MONEY = r"\$\s?" + _N + r"|" + _N + r"\s?(?:\$|dollars?|usd|bucks)"
# amount in a budget context: marker optional ("total budget is 500")
_AMT = r"\$?\s?" + _N + r"\s?(?:\$|dollars?|usd|bucks)?"
_LOC_STOP = {"the", "a", "an", "my", "our", "beach", "work", "school", "dinner", "brunch", "party", "wedding"}

REMEMBER_RE = re.compile(r"\bremember\b|\bsave (?:that|this)\b|\bdon'?t forget\b", re.I)
STRONG_AVOID_RE = re.compile(r"\bnever\b|\bmust not\b|\babsolutely no\b|\bno (?:way|matter what)\b", re.I)
AVOID_TRIGGER_RE = re.compile(r"\b(hate|don'?t like|do not like|dislike|avoid|not a fan of|never|no more|can'?t stand|must not)\b", re.I)
LIKE_TRIGGER_RE = re.compile(r"\b(like|love|prefer|favou?rite|into|want)\b", re.I)
OWN_TRIGGER_RE = re.compile(r"\b(?:i|we)\s+(?:already\s+)?(?:own|have|got|bought)\b", re.I)


def _num(s: str) -> int | None:
    s = s.lower()
    if s.isdigit():
        return int(s)
    return tx.NUMBER_WORDS.get(s)


def _money(m: re.Match) -> float | None:
    raw = next((g for g in m.groups() if g), None)
    return float(raw.replace(",", "")) if raw else None


def _clauses(text: str) -> list[str]:
    # split on sentence ends, ", " (not "1,000"), and "but" so one long comma-separated request
    # doesn't merge e.g. an "I own ..." clause with a "needs a crochet top" clause
    return [c.strip() for c in re.split(r"(?<=[.!?;])\s+|\n+|,\s+(?:and\s+|but\s+)?|\bbut\b", text) if c and c.strip()]


def _colors_in(text: str) -> list[str]:
    t = text.lower()
    found = [c for c in sorted(tx.COLORS, key=len, reverse=True) if tx.term_in_text(c, t)]
    # drop sub-matches like "blue" when "light blue" matched
    return [c for c in found if not any(c != o and c in o for o in found)]


def _garment_phrases(text: str) -> list[str]:
    """'a crochet top and skirt' -> ['crochet top', 'skirt']"""
    t = text.lower()
    nouns = sorted(tx.GARMENTS, key=len, reverse=True)
    pattern = r"((?:(?:" + "|".join(re.escape(d) for d in sorted(tx.DESCRIPTORS | tx.COLORS, key=len, reverse=True)) + r")\s+){0,2})(" + "|".join(re.escape(n) for n in nouns) + r")(?![a-z])"
    out = []
    for m in re.finditer(pattern, t):
        phrase = (m.group(1) + m.group(2)).strip()
        if phrase not in out:
            out.append(phrase)
    return out


def rule_parse(text: str) -> dict:
    t = text.strip()
    low = t.lower()
    data: dict = {}

    # location: after travel phrases (any capitalization), else a Capitalized place after to/in/at
    m = re.search(
        r"\b(?:going to|go to|goin to|trip to|travel(?:ing|ling)? to|fly(?:ing)? to|head(?:ed|ing)? to|"
        r"visit(?:ing)?|vacation in|holiday in|staying in|weekend in|week in|days? in|nights? in)\s+"
        r"([a-z][a-z.'\-]*(?:\s+[a-z][a-z.'\-]*){0,3}?)"
        r"(?=\s+(?:for|with|and|next|this|on|from|to|in|over|during|i|we|my)\b|\s*[,.!?;]|\s*$)", low)
    if m and m.group(1).split()[0] not in _LOC_STOP:
        data["location"] = " ".join(w.capitalize() for w in m.group(1).split())
    else:
        m = (re.search(r"\b(?:to|in|at)\s+((?:[A-Z][a-zA-Z]+)(?:\s+[A-Z][a-zA-Z]+){0,3})", t)
             or re.search(r"\b((?:[A-Z][a-zA-Z]+)(?:\s+[A-Z][a-zA-Z]+)?)\s+(?:trip|vacation|getaway|weekend)\b", t))
        if m and m.group(1) not in {"I", "My", "Beach", "Road", "Work", "Business", "Girls"}:
            data["location"] = m.group(1)

    # duration
    m = re.search(_NUM + r"[\s-]+(?:days?|nights?)\b", low)
    if m:
        data["duration_days"] = _num(m.group(1))
    elif re.search(r"\ba week\b|\bone week\b", low):
        data["duration_days"] = 7
    elif "weekend" in low:
        data["duration_days"] = 2

    # outfits
    plural = re.search(_NUM + r"\s+(?:\w+\s+)?(?:outfits|looks|fits|sets|outfit ideas)\b", low)
    single = re.search(_NUM + r"\s+(?:\w+\s+)?(?:outfit|look)\b", low)
    m = plural or single
    if m and _num(m.group(1)):
        data["number_of_outfits"] = _num(m.group(1))

    # total budget (checked first so "under 50$ total budget is 500$" reads 500 as the total)
    for pat in [
        r"total(?:\s+\w+){0,3}?\s+(?:budget|spend(?:ing)?|cost)\s*(?:is|of|=|:|would be|should be)?\s*"
        r"(?:around|about|up to|under|max(?:imum)?|at most)?\s*(?:" + _AMT + r")",
        r"total\s+(?:of\s+|is\s+)?(?:" + _AMT + r")",
        r"(?:" + _MONEY + r")\s*(?:in\s+)?total\b",
        r"\b" + _N + r"\s+(?:in\s+)?total\b",
        r"(?:overall|whole trip|entire trip)[^.$\d]{0,25}?(?:" + _AMT + r")",
        r"budget\s+(?:is|of)\s*(?:" + _MONEY + r")(?![^.]*outfit)",
    ]:
        m = re.search(pat, low)
        if m:
            data["total_budget"] = _money(m)
            break

    # per-outfit budget
    for pat in [
        r"(?:each|per|every|an?)\s+outfit[^.\d$]{0,40}?(?:" + _AMT + r")",
        r"(?:" + _MONEY + r")\s*(?:per|each|an?|for each|/)\s*outfit",
        r"outfits?\s+(?:that are\s+|each\s+)?(?:under|below|less than|max(?:imum)?|up to|at most|no more than|"
        r"nothing over|not over)\s*(?:" + _AMT + r")",
        r"(?:" + _MONEY + r")\s*each",
        r"(?:nothing over|not over|under|max)\s*(?:" + _MONEY + r")\s*(?:each|apiece|a piece|per look|a look)",
    ]:
        m = re.search(pat, low)
        if m and _money(m) != data.get("total_budget"):
            data["per_outfit_budget"] = _money(m)
            break

    styles: list[str] = []
    for s in tx.STYLES:
        if tx.term_in_text(s, low) and s not in styles:
            styles.append(s)
    if "beach" in low and "beachy" not in styles and re.search(r"beach(?:y)?\s+(?:vibe|aesthetic|look|style)", low):
        styles.append("beachy")
    for s in list(styles):
        for implied in tx.STYLE_IMPLIES.get(s, []):
            if implied not in styles:
                styles.append(implied)

    preferred: list[str] = []
    avoid: list[str] = []
    additional: list[str] = []
    required: list[dict] = []
    owned_phrases: list[str] = []
    strong_avoid = False

    for clause in _clauses(t):
        c = clause.lower()
        if OWN_TRIGGER_RE.search(c):
            owned_phrases += [p for p in _garment_phrases(c[OWN_TRIGGER_RE.search(c).end():]) if p not in owned_phrases]
            continue
        if AVOID_TRIGGER_RE.search(c):
            after = c[AVOID_TRIGGER_RE.search(c).end():]
            avoid += [x for x in _colors_in(after) if x not in avoid]
            for g in _garment_phrases(after):
                if g not in avoid:
                    avoid.append(g)
            for s in tx.STYLES:
                if tx.term_in_text(s, after) and s not in avoid:
                    avoid.append(s)
                    if s in styles:
                        styles.remove(s)
            if STRONG_AVOID_RE.search(c):
                strong_avoid = True
            continue
        colors_here = _colors_in(c)
        if colors_here and (LIKE_TRIGGER_RE.search(c) or "aesthetic" in c or "palette" in c or "vibe" in c):
            preferred += [x for x in colors_here if x not in preferred]
        if re.search(r"\b(needs?|must have|must include|include|requires?|want)\b", c):
            trig = re.search(r"\b(needs?|must have|must include|include|requires?|want)\b", c)
            for g in _garment_phrases(c[trig.end():]):
                if all(r["item"] != g for r in required):
                    target = None
                    m = re.search(r"outfit\s+" + _NUM + r"\b|day\s+" + _NUM + r"\b", c)
                    if m:
                        n = _num(m.group(1) or m.group(2))
                        target = f"outfit_{n}" if n else None
                    required.append({"item": g, "quantity": 1, "required_for_outfit": target})
        for mat in ("linen", "cotton", "silk", "crochet", "denim", "satin", "knit"):
            if LIKE_TRIGGER_RE.search(c) and tx.term_in_text(mat, c) and not required and mat not in additional:
                additional.append(mat)

    if re.search(r"\bneutral\b", low) and "neutral" not in preferred and "neutral" not in avoid:
        preferred.append("neutral")

    occasions = [o for o in tx.OCCASIONS if o != "casual" and tx.term_in_text(o, low)]
    if not occasions:
        if {"beachy", "coastal", "resort"} & set(styles) or "beach" in low:
            occasions = ["beach", "brunch", "sightseeing", "dinner"]
        elif data.get("location") and data.get("duration_days"):
            occasions = ["sightseeing", "brunch", "dinner"]
    elif "beach" in occasions and len(occasions) == 1 and (data.get("duration_days") or 0) > 1:
        occasions = ["beach", "brunch", "sightseeing", "dinner"]

    data.update({
        "styles": styles, "preferred_colors": preferred, "avoid": avoid,
        "required_items": required, "occasions": occasions, "additional_preferences": additional,
        "hard_constraints": ["avoid"] if strong_avoid else [],
        "_owned_phrases": owned_phrases,
        "_remember": bool(REMEMBER_RE.search(t)),
    })
    return data


LLM_SYSTEM = """You convert a shopper's natural-language request into JSON. Output ONLY a JSON object with keys:
location (string|null), duration_days (int|null), number_of_outfits (int|null),
occasions (list of short lowercase words like beach, brunch, sightseeing, dinner, party, work; infer reasonable ones for a trip),
styles (lowercase aesthetic words, e.g. beachy, coastal, minimal, elegant, boho),
preferred_colors (lowercase colors; "neutral" allowed), avoid (lowercase colors/styles/items the user dislikes),
required_items (list of {"item": lowercase garment description, "quantity": int, "required_for_outfit": "outfit_N" or null}),
per_outfit_budget (number|null, USD), total_budget (number|null, USD),
owned_items (list of {"name": e.g. "white sneakers", "category": one of top,bottom,dress,shoes,outerwear,accessory, "colors": [..]}),
remember (true ONLY if the user explicitly asks to remember/save something),
strong_avoid (true only if the user says never / must not),
additional_preferences (list of short lowercase strings for any other preferences).
Rules: unknown scalars -> null, empty lists -> []. Do NOT invent budgets or numbers the user did not state.
Items the user already owns are NOT required_items."""


def _llm_parse(text: str) -> dict | None:
    for _ in range(2):  # retry once
        out = call_llm_json(LLM_SYSTEM, text)
        if isinstance(out, dict):
            return out
    return None


def _resolve_owned(phrases: list[dict], wardrobe: list[dict], user_id: str, remember: bool) -> tuple[list[str], list[dict]]:
    """Match owned-item mentions to existing wardrobe ids or propose new wardrobe items."""
    refs: list[str] = []
    new_items: list[dict] = []
    for ph in phrases:
        name = ph["name"].lower()
        colors = ph.get("colors") or _colors_in(name)
        category = ph.get("category") or tx.kind_category(name)
        match = None
        for w in wardrobe:
            if tx.matches_kind(w, name) or (w.get("name") or "").lower() == name:
                match = w
                break
        if match:
            if match["id"] not in refs:
                refs.append(match["id"])
            continue
        noun = next((n for n in sorted(tx.GARMENTS, key=len, reverse=True) if tx.term_in_text(n, name)), None)
        item = make_wardrobe_item(
            user_id=user_id, name=name, category=category,
            subcategory=noun.replace(" ", "_") if noun else None,
            colors=colors, tags=[], remembered=remember,
        )
        if item["id"] not in refs:
            refs.append(item["id"])
            new_items.append(item)
    return refs, new_items


def parse_request(raw_request: str, session_id: str, user_id: str,
                  wardrobe: list[dict] | None = None, use_llm: bool = True) -> dict:
    """Returns {"request": ShoppingRequest, "new_wardrobe_items": [...], "used_llm": bool,
    "clarification": str|None}."""
    wardrobe = wardrobe or []
    rules = rule_parse(raw_request)
    llm = _llm_parse(raw_request) if (use_llm and llm_available()) else None

    merged = dict(rules)
    if llm:
        for key in ("location", "duration_days", "number_of_outfits", "per_outfit_budget", "total_budget"):
            if llm.get(key) is not None:
                merged[key] = llm[key]
        for key in ("occasions", "styles", "preferred_colors", "avoid", "required_items", "additional_preferences"):
            if llm.get(key):
                merged[key] = llm[key]
        if llm.get("strong_avoid"):
            merged["hard_constraints"] = ["avoid"]

    owned = [{"name": p} for p in rules.get("_owned_phrases", [])]
    if llm and isinstance(llm.get("owned_items"), list):
        owned = [o for o in llm["owned_items"] if isinstance(o, dict) and o.get("name")] or owned
    remember = rules["_remember"] or bool(llm and llm.get("remember") is True)
    refs, new_items = _resolve_owned(owned, wardrobe, user_id, remember)
    merged["owned_item_references"] = refs

    request = normalize_shopping_request(merged, session_id, user_id, raw_request)

    clarification = None
    understood = any([request["number_of_outfits"], request["styles"], request["required_items"],
                      request["occasions"], request["per_outfit_budget"], request["total_budget"]])
    if not understood:
        clarification = ("I couldn't tell what you'd like me to shop for. Could you tell me the occasion or trip, "
                         "how many outfits you need, and your budget?")
    if request["number_of_outfits"] is None:
        request["number_of_outfits"] = 1
        request["hard_constraints"], request["soft_preferences"] = _recompute(request)
    return {"request": request, "new_wardrobe_items": new_items, "used_llm": llm is not None,
            "clarification": clarification}


def _recompute(req: dict):
    from agents.core.contract import derive_constraint_lists
    return derive_constraint_lists(req, {"hard_constraints": req.get("hard_constraints")})


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or (
        "I'm going to San Diego for five days. I need five outfits. Each outfit should be under $50 and my "
        "total budget is $500. I want a beachy neutral aesthetic. One outfit needs a crochet top and skirt. "
        "I like beige and white. I don't like neon colors. I already own white sneakers. Remember that I own them.")
    print(json.dumps(parse_request(text, "session_cli", "user_cli"), indent=2))
