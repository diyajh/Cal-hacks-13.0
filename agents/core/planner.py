"""Trip planner: builds complete outfits, has the Budget Agent check them, and autonomously
replans until every hard constraint holds or MAX_REPLAN_ATTEMPTS is reached (contract §17).

The planner runs inside the orchestrator. It never talks to products directly: it asks the
Search Agent for products, the Style Agent for scores and the Budget Agent for verdicts.
"""
from __future__ import annotations

import asyncio

from agents import config
from agents.core import taxonomy as tx
from agents.core.contract import make_event, wardrobe_item_active
from agents.core.explain import why_it_works
from agents.core.scoring import score_outfit
from agents.products.client import make_search_request

PLANNER = "planner"
CAT_QUERY = {"top": "top", "bottom": "skirt shorts", "dress": "dress", "shoes": "sandals",
             "outerwear": "light jacket", "accessory": "accessory"}
REUSE_LIMIT = {"shoes": 5, "accessory": 5, "outerwear": 5}
DEFAULT_REUSE_LIMIT = 2
PLURAL = {"top": "tops", "bottom": "bottoms", "dress": "dresses", "shoes": "shoes",
          "outerwear": "jackets", "accessory": "accessories"}
WARDROBE_BONUS, OWNED_REF_BONUS, REUSE_BONUS = 12.0, 25.0, 6.0


def _usd(x: float) -> str:
    return f"${x:,.2f}"


def _label(outfit_id: str) -> str:
    return outfit_id.replace("_", " ").capitalize()


class TripPlanner:
    def __init__(self, session_id: str, request: dict, profile: dict | None, wardrobe: list[dict],
                 bus, events: list[dict], state: dict | None = None, on_event=None):
        self.sid = session_id
        self.request = request
        self.profile = profile or {}
        self.wardrobe = [w for w in (wardrobe or []) if wardrobe_item_active(w)]
        self.bus = bus
        self.events = events
        self.on_event = on_event
        state = state or {}
        self.outfits: list[dict] = state.get("outfits", [])
        self.pool: dict[str, dict] = state.get("pool", {})
        self.scores: dict[str, dict] = state.get("scores", {})
        self.item_ids: dict[str, str] = state.get("item_ids", {})

    # ------------------------------------------------------------------ utilities
    def emit(self, events_or_event):
        evs = events_or_event if isinstance(events_or_event, list) else [events_or_event]
        for e in evs:
            self.events.append(e)
            if self.on_event:
                try:
                    self.on_event(e)
                except Exception:  # UI streaming must never break planning
                    pass

    def ev(self, type_, message, outfit_id=None, status="completed", agent=PLANNER):
        self.emit(make_event(self.sid, agent, type_, message, status, outfit_id))

    def state(self) -> dict:
        return {"outfits": self.outfits, "pool": self.pool, "scores": self.scores, "item_ids": self.item_ids}

    def outfit(self, oid: str) -> dict:
        return next(o for o in self.outfits if o["id"] == oid)

    @staticmethod
    def ctx_key(o: dict) -> str:
        return f"{o['occasion']}|{','.join(sorted(o.get('style_modifiers') or []))}"

    def _ctx_for_key(self, key: str) -> dict:
        occ, mods = key.split("|", 1)
        return {"key": key, "occasion": occ or None, "style_modifiers": [m for m in mods.split(",") if m]}

    def score(self, item_id: str, key: str) -> dict | None:
        return self.scores.get(item_id, {}).get(key)

    def _purchase_items(self, o):
        return [p for p in o["picks"].values() if p and p["source"] == "product"]

    def outfit_cost(self, o) -> float:
        return round(sum(p["item"]["price"] for p in self._purchase_items(o)), 2)

    def usage(self, item_id: str, exclude_outfit: str | None = None) -> int:
        return sum(1 for o in self.outfits if o["id"] != exclude_outfit
                   for p in o["picks"].values() if p and p["item"]["id"] == item_id)

    # ------------------------------------------------------------------ agent calls
    async def _style(self, items: list[dict], keys: list[str], outfit_id=None):
        todo = [i for i in items if any(self.score(i["id"], k) is None for k in keys)]
        if not todo:
            return
        scores, evs = await self.bus.style(self.sid, self.request, self.profile,
                                           [self._ctx_for_key(k) for k in keys], todo, outfit_id)
        self.emit(evs)
        for pid, per_key in scores.items():
            self.scores.setdefault(pid, {}).update(per_key)

    async def _search(self, search_request: dict, reason: str = "", outfit_id=None) -> list[dict]:
        products, evs = await self.bus.search(self.sid, search_request, reason, outfit_id)
        self.emit(evs)
        for p in products:
            self.pool[p["id"]] = p
        return products

    def _base_search(self, query_core: str, category: str | None, max_price=None, broad=False,
                     extra_style: list[str] | None = None) -> dict:
        styles = list(extra_style or []) + list(self.request.get("styles") or [])
        word = styles[0] if styles else ""
        colors = [] if broad else [c for c in self.request.get("preferred_colors") or [] if c not in ("neutral", "neutrals")]
        tags = [] if broad else (styles[:2] + list(self.request.get("occasions") or [])[:2])
        if max_price is None:
            max_price = self.request.get("per_outfit_budget")
        return make_search_request(f"{word} {query_core}".strip(), category, colors, tags, max_price, 20)

    # ------------------------------------------------------------------ initial plan
    def _init_outfits(self):
        n = self.request.get("number_of_outfits") or 1
        occs = self.request.get("occasions") or ["casual"]
        days = self.request.get("duration_days")
        self.outfits = []
        for i in range(n):
            occ = occs[i % len(occs)]
            template = ["dress", "shoes"] if occ in tx.DRESS_OCCASIONS else ["top", "bottom", "shoes"]
            self.outfits.append({
                "id": f"outfit_{i + 1}", "day": (i % days) + 1 if days else i + 1, "occasion": occ,
                "template": template, "picks": {s: None for s in template}, "required": {},
                "style_modifiers": [], "excluded": [], "attempts": 0,
            })

    def _set_template(self, o, template):
        old = o["picks"]
        o["template"] = template
        o["picks"] = {s: old.get(s) for s in template}

    def _assign_required(self):
        reqs = []
        for r in self.request.get("required_items") or []:
            reqs += [r] * r["quantity"]
        for r in reqs:
            kind, cat = r["item"], tx.kind_category(r["item"])
            if not cat:
                self.ev("conflict", f"I don't know what kind of garment '{kind}' is; I'll keep it in mind but can't place it.")
                continue
            if r.get("required_for_outfit"):
                candidates = [o for o in self.outfits if o["id"] == r["required_for_outfit"]]
            else:
                # group required pieces together (e.g. "crochet top and skirt" in ONE outfit)
                with_req = [o for o in self.outfits if o["required"] and cat not in o["required"]
                            and not (cat == "dress" and ({"top", "bottom"} & set(o["required"])))
                            and not (cat in ("top", "bottom") and "dress" in o["required"])]
                candidates = with_req + [o for o in self.outfits if not o["required"]]
            for o in candidates:
                if cat in o["required"]:
                    continue
                if cat in ("top", "bottom") and "dress" in o["template"]:
                    self._set_template(o, ["top", "bottom", "shoes"])
                elif cat == "dress" and "top" in o["template"]:
                    self._set_template(o, ["dress", "shoes"])
                elif cat not in o["template"]:
                    self._set_template(o, o["template"] + [cat])
                o["required"][cat] = kind
                break

    async def plan(self) -> list[dict]:
        self._init_outfits()
        self._assign_required()
        self.ev("planning", f"Planning {len(self.outfits)} outfits: " +
                ", ".join(f"Day {o['day']} {o['occasion']}" for o in self.outfits), status="working")

        needs: dict[tuple, dict] = {}
        for o in self.outfits:
            for slot in o["template"]:
                kind = o["required"].get(slot)
                key = ("kind", kind) if kind else ("cat", slot)
                if key not in needs:
                    needs[key] = self._base_search(kind or CAT_QUERY[slot], slot)
        for slot in ("top", "bottom", "shoes"):
            needs.setdefault(("cat", slot), self._base_search(CAT_QUERY[slot], slot))
        if any(o["occasion"] in tx.DRESS_OCCASIONS for o in self.outfits):
            needs.setdefault(("cat", "dress"), self._base_search("dress", "dress"))
            needs.setdefault(("cat", "shoes-dressy"), self._base_search("heels", "shoes", extra_style=["elegant"]))

        results = await asyncio.gather(*(self._search(req, "initial search") for req in needs.values()))
        products = {p["id"]: p for batch in results for p in batch}
        keys = sorted({self.ctx_key(o) for o in self.outfits})
        await self._style(list(products.values()) + self.wardrobe, keys)

        for o in self.outfits:
            self._build_outfit(o)
        return await self.check_and_replan([o["id"] for o in self.outfits])

    # ------------------------------------------------------------------ building
    def _candidates(self, o, slot, max_price=None, marginal=False):
        kind = o["required"].get(slot)
        key = self.ctx_key(o)
        out = []
        for item in list(self.pool.values()) + self.wardrobe:
            is_w = item in self.wardrobe
            cat = item.get("category")
            if cat != slot or (not is_w and item["id"] in o["excluded"]):
                continue
            if kind and not tx.matches_kind(item, kind):
                continue
            s = self.score(item["id"], key)
            if s is None or s["excluded"]:
                continue
            used_elsewhere = self.usage(item["id"], exclude_outfit=o["id"])
            if not is_w:
                if used_elsewhere >= REUSE_LIMIT.get(slot, DEFAULT_REUSE_LIMIT):
                    continue
                price = 0.0 if (marginal and used_elsewhere) else item["price"]
                if max_price is not None and price > max_price:
                    continue
            eff = s["score"]
            if is_w:
                bonus = OWNED_REF_BONUS if item["id"] in (self.request.get("owned_item_references") or []) else WARDROBE_BONUS
                eff += bonus if s["occasion"] >= 60 else bonus * 0.3  # owned sneakers shouldn't win at dinner
            elif used_elsewhere:
                eff += REUSE_BONUS
                # avoid near-duplicate outfits: penalize pairing pieces that are already paired elsewhere
                mine = {p["item"]["id"] for sl, p in o["picks"].items() if p and sl != slot and p["source"] == "product"}
                for other in self.outfits:
                    if other["id"] == o["id"]:
                        continue
                    theirs = {p["item"]["id"] for p in other["picks"].values() if p}
                    if item["id"] in theirs and mine & theirs:
                        eff -= 20
            budget = self.request.get("per_outfit_budget")
            if budget and not is_w:  # mild price awareness; the Budget Agent enforces the hard limit
                share = budget / max(1, len(o["template"]) - (1 if "shoes" in o["template"] and self.wardrobe else 0))
                eff -= max(0.0, item["price"] - share * 1.5) * 0.5
            out.append((eff, -(item.get("price") or 0), item, is_w, s))
        out.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return out

    def _pick(self, o, slot, entry, locked=False):
        _, _, item, is_w, _ = entry
        o["picks"][slot] = {"source": "wardrobe" if is_w else "product", "item": item,
                            "required": o["required"].get(slot), "locked": locked}

    def _build_outfit(self, o, announce=True):
        if "dress" in o["template"] and not o["required"].get("dress") and not self._candidates(o, "dress"):
            self._set_template(o, ["top", "bottom", "shoes"])
        for slot in o["template"]:
            cur = o["picks"].get(slot)
            if cur and cur.get("locked"):
                continue
            cands = self._candidates(o, slot)
            o["picks"][slot] = None
            if cands:
                self._pick(o, slot, cands[0])
        if announce:
            self.ev("outfit_created", f"Created {_label(o['id'])} (Day {o['day']}, {o['occasion']}): "
                    + self._describe(o) + f" — new purchases {_usd(self.outfit_cost(o))}", o["id"])

    def _describe(self, o) -> str:
        parts = []
        for slot in o["template"]:
            p = o["picks"].get(slot)
            if not p:
                parts.append(f"[no {slot} found]")
            elif p["source"] == "wardrobe":
                parts.append(f"your {p['item']['name']}")
            else:
                parts.append(f"{p['item']['name']} {_usd(p['item']['price'])}")
        return " + ".join(parts)

    # ------------------------------------------------------------------ check / replan loop
    async def check_and_replan(self, target_ids: list[str]) -> list[dict]:
        """Returns the hard violations that could NOT be resolved (empty = success)."""
        remaining: list[dict] = []
        for attempt in range(config.MAX_REPLAN_ATTEMPTS + 1):
            violations, evs = await self.bus.check(self.sid, self.request, self.to_contract_outfits(), target_ids)
            self.emit(evs)
            hard = [v for v in violations if v["severity"] == "hard"]
            if not hard:
                for oid in target_ids:
                    o = self.outfit(oid)
                    self.ev("outfit_accepted", f"{_label(oid)} accepted — {self._describe(o)}", oid)
                return []
            if attempt == config.MAX_REPLAN_ATTEMPTS:
                remaining = hard
                break
            for v in hard:
                await self._resolve(v, attempt + 1)
        for v in remaining:
            v["resolution"] = "ask_user"
        bad = {v["outfit_id"] for v in remaining}
        for oid in target_ids:
            if oid not in bad:
                self.ev("outfit_accepted", f"{_label(oid)} accepted", oid)
        self.ev("conflict", f"Stopped after {config.MAX_REPLAN_ATTEMPTS} replanning attempts; "
                f"{len(remaining)} constraint(s) still unresolved.", status="failed")
        return remaining

    async def _resolve(self, v: dict, attempt: int):
        c, oid = v["constraint"], v.get("outfit_id")
        if c == "per_outfit_budget" and oid:
            o = self.outfit(oid)
            self.ev("replanning", f"Replanning {_label(oid)} (attempt {attempt}/{config.MAX_REPLAN_ATTEMPTS}): "
                    f"{_usd(v['actual'])} is {_usd(v['actual'] - v['expected'])} over the {_usd(v['expected'])} limit.",
                    oid, status="working")
            await self._reduce_outfit_cost(o, round(v["actual"] - v["expected"], 2))
        elif c == "complete_outfit" and oid:
            o = self.outfit(oid)
            for slot in o["template"]:
                if not o["picks"].get(slot):
                    await self._broaden_slot(o, slot)
        elif c == "required_items":
            kind = v["expected"]
            cat = tx.kind_category(kind)
            target = next((o for o in self.outfits if o["required"].get(cat) == kind), None) or self.outfits[0]
            target["required"][cat] = kind
            if cat not in target["template"]:
                self._set_template(target, ["top", "bottom", "shoes"] if cat in ("top", "bottom") else [cat, "shoes"])
            await self._broaden_slot(target, cat)
        elif c == "total_budget":
            self.ev("replanning", f"Trip total {_usd(v['actual'])} is over the {_usd(v['expected'])} budget; "
                    "looking for cheaper pieces or pieces to reuse.", status="working")
            await self._reduce_plan_cost(round(v["actual"] - v["expected"], 2))
        elif c == "avoid" and oid:
            o = self.outfit(oid)
            for slot, p in o["picks"].items():
                if p and p["item"]["name"] == v["actual"]:
                    if p["source"] == "product":
                        o["excluded"].append(p["item"]["id"])
                    o["picks"][slot] = None
            self._build_outfit(o)

    async def _broaden_slot(self, o, slot):
        kind = o["required"].get(slot)
        self.ev("replanning", f"No suitable {kind or slot} yet for {_label(o['id'])}; broadening the search.",
                o["id"], status="working")
        await self._search(self._base_search(kind or CAT_QUERY[slot], slot, broad=True), "broadened search", o["id"])
        await self._style(list(self.pool.values()) + self.wardrobe, [self.ctx_key(o)], o["id"])
        cands = self._candidates(o, slot)
        if cands:
            self._pick(o, slot, cands[0])
            self.ev("replacement_found", f"Found {self._describe_item(cands[0])} for {_label(o['id'])}", o["id"])

    @staticmethod
    def _describe_item(entry) -> str:
        _, _, item, is_w, s = entry
        if is_w:
            return f"your {item['name']} (already owned, $0)"
        return f"{item['name']} ({_usd(item['price'])}, style match {round(s['score'])}/100)"

    async def _reduce_outfit_cost(self, o, overage: float):
        replaceable = [(slot, p) for slot, p in o["picks"].items() if p and p["source"] == "product" and not p["locked"]]
        replaceable.sort(key=lambda sp: (sp[1]["required"] is not None, -sp[1]["item"]["price"]))
        for slot, p in replaceable:
            target = round(p["item"]["price"] - overage, 2)
            if target < 5:
                continue
            if await self.replace_slot(o, slot, target, why=f"to bring {_label(o['id'])} under budget"):
                return True
        # no single swap fixes it: cheapen pieces (priciest first) and let the next round re-check
        for slot, p in sorted(replaceable, key=lambda sp: -sp[1]["item"]["price"]):
            if p["item"]["id"] in o.get("tried_partial", []):
                continue
            o.setdefault("tried_partial", []).append(p["item"]["id"])
            if await self.replace_slot(o, slot, round(p["item"]["price"] - 0.01, 2),
                                       why="for a partial saving", prefer_cheapest=True):
                return True
        return False

    async def _reduce_plan_cost(self, overage: float):
        picks = [(o, slot, p) for o in self.outfits for slot, p in o["picks"].items()
                 if p and p["source"] == "product" and not p["locked"]]
        picks.sort(key=lambda x: (x[2]["required"] is not None, -x[2]["item"]["price"]))
        for o, slot, p in picks:
            others = self.outfit_cost(o) - p["item"]["price"]
            cap = round(p["item"]["price"] - min(overage, p["item"]["price"] - 0.01), 2)
            if self.request.get("per_outfit_budget") is not None:
                cap = min(cap, self.request["per_outfit_budget"] - others)
            if cap >= 0 and await self.replace_slot(o, slot, cap, why="to fit the total budget", marginal=True):
                return True
        return False

    async def replace_slot(self, o, slot, max_price, why="", prefer_cheapest=False, marginal=False,
                           style_modifiers: list[str] | None = None) -> bool:
        cur = o["picks"].get(slot)
        kind = o["required"].get(slot)
        what = kind or PLURAL[slot]
        cur_desc = f"{cur['item']['name']} ({_usd(cur['item']['price'])})" if cur and cur["source"] == "product" else (
            f"your {cur['item']['name']}" if cur else f"empty {slot}")
        ask = (f"looking for {what} you already own or are already buying" if max_price < 1
               else f"requesting {what} under {_usd(max_price)}")
        self.ev("replanning", f"Replacing {cur_desc} in {_label(o['id'])} {why}; {ask}.", o["id"], status="working")
        if cur and cur["source"] == "product":
            o["excluded"].append(cur["item"]["id"])

        mods = style_modifiers if style_modifiers is not None else o.get("style_modifiers")
        await self._search(self._base_search(kind or CAT_QUERY[slot], slot, max_price=max_price, extra_style=mods),
                           "replacement search", o["id"])
        await self._style(list(self.pool.values()) + self.wardrobe, [self.ctx_key(o)], o["id"])
        cands = self._candidates(o, slot, max_price=max_price, marginal=marginal)
        if prefer_cheapest:
            cands.sort(key=lambda x: (x[2].get("price") or 0) if not x[3] else -1)
        if not cands:
            self.ev("replanning", f"No {what} {'available' if max_price < 1 else 'under ' + _usd(max_price)} matched your constraints; trying another piece.",
                    o["id"], status="failed")
            return False
        self._pick(o, slot, cands[0])
        self.ev("replacement_found", f"Swapped in {self._describe_item(cands[0])} for {_label(o['id'])}. "
                f"New outfit cost {_usd(self.outfit_cost(o))}.", o["id"])
        return True

    # ------------------------------------------------------------------ contract output
    def _item_id(self, source: str, item_id: str) -> str:
        key = f"{source}:{item_id}"
        if key not in self.item_ids:
            self.item_ids[key] = f"outfit_item_{len(self.item_ids) + 1}"
        return self.item_ids[key]

    def to_contract_outfits(self) -> list[dict]:
        used_in: dict[str, list[str]] = {}
        for o in self.outfits:
            for p in o["picks"].values():
                if p:
                    used_in.setdefault(f"{p['source']}:{p['item']['id']}", []).append(o["id"])
        styles = self.request.get("styles") or []
        out = []
        for idx, o in enumerate(self.outfits):
            items, item_scores, raw_items = [], [], []
            key = self.ctx_key(o)
            for slot in o["template"]:
                p = o["picks"].get(slot)
                if not p:
                    continue
                k = f"{p['source']}:{p['item']['id']}"
                is_prod = p["source"] == "product"
                items.append({
                    "id": self._item_id(p["source"], p["item"]["id"]),
                    "source_type": p["source"],
                    "product": p["item"] if is_prod else None,
                    "wardrobe_item": None if is_prod else p["item"],
                    "purchase_required": is_prod,
                    "reused": len(used_in[k]) > 1,
                    "used_in_outfits": used_in[k],
                })
                raw_items.append(p["item"])
                s = self.score(p["item"]["id"], key)
                if s:
                    item_scores.append(s)
            cost = self.outfit_cost(o)
            match, breakdown = score_outfit(item_scores, raw_items, cost, self.request.get("per_outfit_budget"))
            values = [i["product"]["price"] if i["product"] else (i["wardrobe_item"].get("estimated_value") or 0)
                      for i in items]
            style_word = (o.get("style_modifiers") or [None])[0] or (styles[idx % len(styles)] if styles else "")
            title = f"{style_word.title()} {tx.OCCASION_TITLES.get(o['occasion'], o['occasion'].title())}".strip()
            limit = self.request.get("per_outfit_budget")
            out.append({
                "id": o["id"], "title": title, "day": o["day"], "occasion": o["occasion"],
                "match_score": match, "score_breakdown": breakdown, "items": items,
                "total_value": round(sum(values), 2), "new_purchase_cost": cost,
                "why_it_works": "",
                "constraints_satisfied": len(items) == len(o["template"]) and (limit is None or cost <= limit),
            })
            out[-1]["why_it_works"] = why_it_works(out[-1], self.request, list(o["required"].values()))
        return out
