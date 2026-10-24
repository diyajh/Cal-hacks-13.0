"""The work each specialist agent performs. Shared by the Fetch.ai uAgents and the local bus,
so behaviour is identical in both modes. Each handler returns (result, events)."""
from __future__ import annotations

from agents.core import taxonomy as tx
from agents.core.contract import make_event, make_violation
from agents.core.scoring import build_context, score_item
from agents.products.client import search_products

SEARCH, STYLE, BUDGET = "search_agent", "style_agent", "budget_agent"


def _usd(x: float) -> str:
    return f"${x:,.2f}"


# --------------------------------------------------------------------------- SEARCH AGENT

def search_agent_handle(session_id: str, search_request: dict, reason: str = "",
                        outfit_id: str | None = None) -> tuple[list[dict], list[dict]]:
    events = []
    desc = search_request["query"]
    if search_request.get("max_price") is not None:
        desc += f" under {_usd(search_request['max_price'])}"
    events.append(make_event(session_id, SEARCH, "search_started",
                             f"Searching for {desc}" + (f" ({reason})" if reason else ""), "working", outfit_id))
    try:
        products, source = search_products(search_request)
    except Exception as exc:  # never crash the agent; report honestly
        events.append(make_event(session_id, SEARCH, "search_completed", f"Search failed: {exc}", "failed", outfit_id))
        return [], events
    src = "live product service" if source == "product_service" else "fallback catalog"
    events.append(make_event(session_id, SEARCH, "search_completed",
                             f"Found {len(products)} products for '{search_request['query']}' from {src}",
                             "completed", outfit_id))
    return products, events


# --------------------------------------------------------------------------- STYLE AGENT

def style_agent_handle(session_id: str, request: dict, profile: dict | None, contexts: list[dict],
                       products: list[dict], outfit_id: str | None = None) -> tuple[dict, list[dict]]:
    """contexts: [{"key": str, "occasion": str|None, "style_modifiers": [..]}]
    returns scores[product_id][key] = score dict"""
    scores: dict = {}
    excluded = 0
    for p in products:
        scores[p["id"]] = {}
        for c in contexts:
            ctx = build_context(request, profile, c.get("occasion"), c.get("style_modifiers"))
            s = score_item(p, ctx)
            scores[p["id"]][c["key"]] = s
        if any(v["excluded"] for v in scores[p["id"]].values()):
            excluded += 1
    best = None
    for p in products:
        vals = [v["score"] for v in scores[p["id"]].values() if not v["excluded"]]
        if vals and (best is None or max(vals) > best[1]):
            best = (p, max(vals))
    msg = f"Evaluated {len(products)} products against your style profile"
    if excluded:
        msg += f"; excluded {excluded} with avoided colors/styles"
    if best:
        msg += f". Top pick: {best[0]['name']} ({round(best[1])}/100)"
    return scores, [make_event(session_id, STYLE, "style_evaluated", msg, "completed", outfit_id)]


# --------------------------------------------------------------------------- BUDGET / CONSTRAINT AGENT

def _outfit_cost(outfit: dict) -> float:
    return round(sum(i["product"]["price"] for i in outfit["items"]
                     if i["source_type"] == "product" and i["purchase_required"]), 2)


def _complete(outfit: dict) -> bool:
    cats = {(i["product"] or i["wardrobe_item"]).get("category") for i in outfit["items"]}
    return "shoes" in cats and ("dress" in cats or {"top", "bottom"} <= cats)


def budget_agent_handle(session_id: str, request: dict, outfits: list[dict],
                        check_outfit_ids: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Checks HARD constraints on contract-format outfits. Returns (violations, events)."""
    events, violations = [], []
    limit = request.get("per_outfit_budget")
    check_ids = set(check_outfit_ids) if check_outfit_ids else {o["id"] for o in outfits}

    for o in outfits:
        if o["id"] not in check_ids:
            continue
        cost = _outfit_cost(o)
        if not _complete(o):
            v = make_violation("complete_outfit", "top+bottom or dress, plus shoes", "incomplete", o["id"],
                               f"{o['title']} is missing a piece.")
            violations.append(v)
            events.append(make_event(session_id, BUDGET, "constraint_violation", v["message"], "completed", o["id"]))
        if limit is not None and cost > limit:
            v = make_violation("per_outfit_budget", limit, cost, o["id"],
                               f"Outfit exceeds the per-outfit budget by {_usd(cost - limit)}.")
            violations.append(v)
            events.append(make_event(session_id, BUDGET, "constraint_violation",
                                     f"Rejected {o['id'].replace('_', ' ')}: {_usd(cost)} exceeds the {_usd(limit)} limit.",
                                     "completed", o["id"]))
        elif limit is not None:
            events.append(make_event(session_id, BUDGET, "constraint_check",
                                     f"{o['id'].replace('_', ' ').capitalize()}: {_usd(cost)} ≤ {_usd(limit)}. Valid.",
                                     "completed", o["id"]))
        if "avoid" in (request.get("hard_constraints") or []):
            for it in o["items"]:
                data = it["product"] or it["wardrobe_item"]
                for a in request.get("avoid") or []:
                    if tx.term_in_text(a, tx.product_text(data)):
                        v = make_violation("avoid", f"no {a}", data["name"], o["id"], f"{data['name']} contains '{a}'.")
                        violations.append(v)

    # plan-level checks
    unique: dict[str, float] = {}
    for o in outfits:
        for it in o["items"]:
            if it["source_type"] == "product" and it["purchase_required"]:
                unique[it["product"]["id"]] = it["product"]["price"]
    total = round(sum(unique.values()), 2)
    tb = request.get("total_budget")
    if tb is not None:
        if total > tb:
            v = make_violation("total_budget", tb, total, None,
                               f"Trip total {_usd(total)} exceeds the {_usd(tb)} total budget by {_usd(total - tb)}.")
            violations.append(v)
            events.append(make_event(session_id, BUDGET, "constraint_violation", v["message"]))
        else:
            events.append(make_event(session_id, BUDGET, "constraint_check",
                                     f"Trip total {_usd(total)} (each item counted once) is within the {_usd(tb)} budget."))

    n = request.get("number_of_outfits")
    if n and len(outfits) != n:
        v = make_violation("number_of_outfits", n, len(outfits), None, f"Planned {len(outfits)} outfits; {n} requested.")
        violations.append(v)
        events.append(make_event(session_id, BUDGET, "constraint_violation", v["message"]))

    for req_item in request.get("required_items") or []:
        found = 0
        for o in outfits:
            if req_item.get("required_for_outfit") and o["id"] != req_item["required_for_outfit"]:
                continue
            found += sum(1 for it in o["items"] if tx.matches_kind(it["product"] or it["wardrobe_item"], req_item["item"]))
        if found < req_item["quantity"]:
            v = make_violation("required_items", req_item["item"], found, req_item.get("required_for_outfit"),
                               f"Required item '{req_item['item']}' is not in the plan.")
            violations.append(v)
            events.append(make_event(session_id, BUDGET, "constraint_violation", v["message"]))
    return violations, events
