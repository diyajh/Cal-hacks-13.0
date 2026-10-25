"""Conversational modification -> structured edit actions (contract §21).

Rule-based so it is predictable during the demo. Produces:
{
  "target_outfit_ids": [...], "replace_all": bool, "replace_categories": [...], "keep_categories": [...],
  "style_modifiers": [...], "cheaper": bool, "budget_changes": {...}, "add_avoid": [...],
  "bought": [{"kind": str, "outfit_id": str|None}], "remember": bool, "understood": bool
}
"""
from __future__ import annotations

import re

from agents.core import taxonomy as tx
from agents.core.parser import REMEMBER_RE, _colors_in, _garment_phrases

_WORDNUM = "|".join(sorted(list(tx.NUMBER_WORDS) + list(tx.ORDINALS), key=len, reverse=True))
MOD_SYNONYMS = {
    "elegant": "elegant", "fancy": "elegant", "fancier": "elegant", "formal": "elegant", "classy": "elegant",
    "dressy": "dressy", "dressier": "dressy", "sophisticated": "elegant", "polished": "classic",
    "casual": "casual", "relaxed": "casual", "comfy": "comfortable", "comfier": "comfortable",
    "comfortable": "comfortable", "boho": "boho", "beachy": "beachy", "minimal": "minimal",
    "edgy": "edgy", "sporty": "sporty", "romantic": "romantic", "chic": "chic", "colorful": "colorful",
    "preppy": "preppy", "coastal": "coastal", "classic": "classic", "vintage": "vintage",
}


def _n(word: str) -> int | None:
    w = word.lower()
    if w.isdigit():
        return int(w)
    return tx.NUMBER_WORDS.get(w) or tx.ORDINALS.get(w)


def _targets(msg: str, outfits: list[dict]) -> list[str]:
    ids = []
    for m in re.finditer(r"outfit\s*(?:#|number\s*|no\.?\s*)?(\d+|" + _WORDNUM + r")\b", msg):
        n = _n(m.group(1))
        if n:
            ids.append(outfits[-1]["id"] if n == -1 else f"outfit_{n}")
    for m in re.finditer(r"\b(" + "|".join(tx.ORDINALS) + r")\s+(?:outfit|look|one)\b", msg):
        n = tx.ORDINALS[m.group(1)]
        ids.append(outfits[-1]["id"] if n == -1 else f"outfit_{n}")
    for m in re.finditer(r"\bday\s*(\d+|" + _WORDNUM + r")\b", msg):
        n = _n(m.group(1))
        ids += [o["id"] for o in outfits if o["day"] == n][:1]
    valid = {o["id"] for o in outfits}
    out = []
    for i in ids:
        if i in valid and i not in out:
            out.append(i)
    return out


def _cats(phrases: list[str]) -> list[str]:
    out = []
    for p in phrases:
        c = tx.kind_category(p)
        if c and c not in out:
            out.append(c)
    return out


def interpret_modification(message: str, target_outfit_id: str | None, outfits: list[dict]) -> dict:
    msg = message.lower().strip()
    act = {"target_outfit_ids": [], "replace_all": False, "replace_categories": [], "keep_categories": [],
           "style_modifiers": [], "cheaper": False, "budget_changes": {}, "add_avoid": [], "bought": [],
           "replacement_budget": None, "remember": bool(REMEMBER_RE.search(msg)), "understood": False}

    targets = _targets(msg, outfits)
    if target_outfit_id and target_outfit_id not in targets:
        targets.insert(0, target_outfit_id)
    act["target_outfit_ids"] = targets

    # budgets
    m = re.search(r"(?:each|per|every)\s+outfit[^$\d]{0,30}\$?\s?(\d+(?:\.\d+)?)|\$\s?(\d+(?:\.\d+)?)\s*(?:per|each|an?)\s+outfit", msg)
    if m:
        act["budget_changes"]["per_outfit_budget"] = float(m.group(1) or m.group(2))
    # A targeted replacement can carry its own cap without changing the whole trip.
    # Example: “replace the top in outfit 2 with something under $20”.
    m = re.search(r"\b(?:under|below|less than|up to|at most)\s*\$?\s*(\d+(?:\.\d+)?)\b", msg)
    if m and "per_outfit_budget" not in act["budget_changes"]:
        act["replacement_budget"] = float(m.group(1))
    m = re.search(r"total(?:\s+budget)?[^$\d]{0,25}\$?\s?(\d+(?:\.\d+)?)|budget\s+(?:is|to|of)\s+(?:now\s+)?\$?\s?(\d+(?:\.\d+)?)(?![^.]*outfit)", msg)
    if m and "per_outfit_budget" not in act["budget_changes"] or (m and "total" in msg):
        act["budget_changes"]["total_budget"] = float(m.group(1) or m.group(2))

    # bought / own
    m = re.search(r"\b(?:i|we)\s+(?:already\s+)?(?:bought|purchased|got|own|have)\b(.*)", msg)
    if m:
        rest = m.group(1)
        for ph in _garment_phrases(rest):
            act["bought"].append({"kind": ph.replace("the ", ""), "outfit_id": (_targets(rest, outfits) or targets or [None])[0]})
        msg_wo_bought = msg[:m.start()]
    else:
        msg_wo_bought = msg

    # keep / replace
    keep_m = re.search(r"\bkeep\b(.*?)(?=\bbut\b|\breplace\b|\bswap\b|\bchange\b|$)", msg_wo_bought)
    if keep_m:
        act["keep_categories"] = _cats(_garment_phrases(keep_m.group(1)))
    rep_m = re.search(r"\b(replace|swap|change|switch|different|another|new|hate|don'?t like|dislike|redo|get rid of)\b(.*)", msg_wo_bought)
    if rep_m:
        phrases = _garment_phrases(re.split(r"\bkeep\b", rep_m.group(2))[0])
        cats = [c for c in _cats(phrases) if c not in act["keep_categories"]]
        if targets:
            act["replace_categories"] = cats
            if not cats and not act["keep_categories"]:
                act["replace_all"] = True
        elif phrases and re.search(r"\b(hate|don'?t like|dislike|no more|never)\b", msg_wo_bought):
            # no outfit referenced -> a general dislike becomes an avoid preference
            act["add_avoid"] += [p for p in phrases if p not in act["add_avoid"]]
        elif cats:
            act["replace_categories"] = cats
    if re.search(r"\b(hate|don'?t like|dislike|no more|never)\b", msg_wo_bought) and not targets:
        after = re.split(r"\b(?:hate|don'?t like|dislike|no more|never)\b", msg_wo_bought, 1)[1]
        act["add_avoid"] += [c for c in _colors_in(after) if c not in act["add_avoid"]]

    # style modifiers
    for word, canon in MOD_SYNONYMS.items():
        if re.search(r"\b" + word + r"\b", msg_wo_bought) and canon not in act["style_modifiers"]:
            if not any(canon == a for a in act["add_avoid"]):
                act["style_modifiers"].append(canon)
    if re.search(r"\bcheaper\b|\bless expensive\b|\bsave money\b|\bbudget[- ]friendly\b", msg):
        act["cheaper"] = True
    if act["style_modifiers"] and targets and not (act["replace_categories"] or act["replace_all"] or act["keep_categories"]):
        act["replace_all"] = True
    if act["cheaper"] and targets and not act["replace_categories"]:
        act["replace_all"] = True

    act["understood"] = bool(act["replace_all"] or act["replace_categories"] or act["budget_changes"]
                             or act["replacement_budget"] is not None or act["add_avoid"] or act["bought"]
                             or act["style_modifiers"] or act["cheaper"])
    return act
