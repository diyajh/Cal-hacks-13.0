"""Orchestration entry points used by the Fetch orchestrator agent (and by FastAPI as a fallback).

    result = await plan_shopping(raw_request, user_id, session_id, profile, wardrobe, bus)
    result = await modify_shopping(modification_request, profile, wardrobe, bus)

Both return a PlanResult dict:
{
  "final_recommendation": FinalRecommendation,   # contract §20 — send this to the frontend
  "wardrobe_items_to_save": [WardrobeItem],      # Person 2 persists these (memory rules §9/§10)
  "conflict": ConstraintConflict | None,         # contract §18, when status == needs_user_input
  "profile_updates": dict | None                 # explicit preference changes (e.g. new avoids)
}
"""
from __future__ import annotations

import copy
import json
import logging

from agents import config
from agents.core import taxonomy as tx
from agents.core.bus import LocalBus
from agents.core.contract import empty_final_recommendation, make_event, make_wardrobe_item, derive_constraint_lists
from agents.core.modifier import interpret_modification
from agents.core.parser import parse_request
from agents.core.planner import TripPlanner, _usd

log = logging.getLogger("agents.engine")
ORCH = "orchestrator"

# ----------------------------------------------------------------------------- session store
_SESSIONS: dict[str, dict] = {}


def save_session(session_id: str, data: dict) -> None:
    _SESSIONS[session_id] = data
    try:
        config.SESSION_DIR.mkdir(exist_ok=True)
        (config.SESSION_DIR / f"{session_id}.json").write_text(json.dumps(data))
    except OSError as exc:
        log.warning("could not persist session %s: %s", session_id, exc)


def load_session(session_id: str) -> dict | None:
    if session_id in _SESSIONS:
        return _SESSIONS[session_id]
    path = config.SESSION_DIR / f"{session_id}.json"
    if path.exists():
        try:
            _SESSIONS[session_id] = json.loads(path.read_text())
            return _SESSIONS[session_id]
        except (OSError, ValueError):
            return None
    return None


# ----------------------------------------------------------------------------- helpers
def _result(rec, wardrobe_new=None, conflict=None, profile_updates=None) -> dict:
    return {"final_recommendation": rec, "wardrobe_items_to_save": wardrobe_new or [],
            "conflict": conflict, "profile_updates": profile_updates}


def _conflict(remaining: list[dict], request: dict, planner: TripPlanner) -> dict:
    cons = sorted({v["constraint"] for v in remaining})
    limit = request.get("per_outfit_budget")
    msg, options = "I couldn't satisfy every constraint with the available products.", []
    budget_v = [v for v in remaining if v["constraint"] == "per_outfit_budget"]
    missing_req = [v for v in remaining if v["constraint"] == "required_items"]
    if missing_req and limit is not None:
        kind = missing_req[0]["expected"]
        cons = sorted(set(cons) | {"per_outfit_budget", "required_items"})
        msg = f"I couldn't find a complete outfit with a {kind} under {_usd(limit)} with the available products."
        options = [f"Keep the {_usd(limit)} budget and change the requested pieces",
                   "Keep the requested pieces and increase the budget"]
    elif budget_v:
        o = planner.outfit(budget_v[0]["outfit_id"])
        kinds = list(o["required"].values())
        if kinds:
            cons = sorted(set(cons) | {"required_items"})
            msg = (f"I couldn't find a complete {' and '.join(kinds)} outfit under {_usd(limit)} "
                   "with the available products.")
            options = [f"Keep the {_usd(limit)} budget and change the requested pieces",
                       f"Keep the requested pieces and increase the budget to about {_usd(budget_v[0]['actual'])}"]
        else:
            msg = f"I couldn't build {o['id'].replace('_', ' ')} under {_usd(limit)} with the available products."
            options = [f"Increase the per-outfit budget to about {_usd(budget_v[0]['actual'])}",
                       "Let me reuse more pieces from other outfits", "Drop this outfit"]
    elif any(v["constraint"] == "total_budget" for v in remaining):
        v = next(v for v in remaining if v["constraint"] == "total_budget")
        msg = f"The cheapest valid plan I found costs {_usd(v['actual'])}, over your {_usd(v['expected'])} total budget."
        options = [f"Increase the total budget to {_usd(v['actual'])}", "Plan fewer outfits",
                   "Reuse more pieces across outfits"]
    elif any(v["constraint"] == "required_items" for v in remaining):
        v = next(v for v in remaining if v["constraint"] == "required_items")
        msg = f"I couldn't find a '{v['expected']}' that fits your other constraints."
        options = [f"Drop the {v['expected']} requirement", "Suggest a similar item instead", "Increase the budget"]
    elif any(v["constraint"] == "complete_outfit" for v in remaining):
        msg = "I couldn't find enough matching pieces to complete every outfit."
        options = ["Relax the color/style preferences", "Increase the budget", "Plan fewer outfits"]
    return {"status": "needs_user_input", "message": msg, "conflicting_constraints": cons, "options": options}


def _finalize(planner: TripPlanner, request: dict, events: list[dict], remaining: list[dict],
              session_id: str, conflict: dict | None, intro: str | None = None) -> dict:
    outfits = planner.to_contract_outfits()
    unique: dict[str, float] = {}
    owned: dict[str, dict] = {}
    reused: dict[str, dict] = {}
    candidate_reused: set[str] = set()
    for o in outfits:
        for it in o["items"]:
            if it["source_type"] == "product":
                unique[it["product"]["id"]] = it["product"]["price"]
            else:
                owned[it["id"]] = it
            if it["source_type"] == "wardrobe":
                reused[it["id"]] = it
            elif len(it.get("used_in_outfits") or []) > 1:
                candidate_reused.add(it["product"]["id"])
    total = round(sum(unique.values()), 2)
    ok = not remaining
    status = "completed" if ok else "needs_user_input"
    rec = empty_final_recommendation(session_id, status, "", request, events)
    rec.update({
        "outfits": outfits, "total_new_purchase_cost": total, "total_budget": request.get("total_budget"),
        "owned_items_used": list(owned.values()), "reused_items": list(reused.values()),
        "constraint_violations": remaining, "all_constraints_satisfied": ok,
        "wardrobe_reused_count": len(reused),
        "unique_purchase_count": len(unique),
        "purchases_avoided": len(reused),
        "outfits_unlocked": sum(1 for o in outfits if any(i["source_type"] == "product" for i in o["items"])),
        "wardrobe_value_avoided": round(sum((i.get("wardrobe_item") or {}).get("estimated_value") or 0 for i in reused.values()), 2),
        "candidate_reused_count": len(candidate_reused),
    })
    if ok:
        parts = [intro or f"I created {len(outfits)} outfit{'s' if len(outfits) != 1 else ''}"
                 + (f" for {request['location']}" if request.get("location") else "") + " within your constraints."]
        if request.get("total_budget") is not None:
            parts.append(f"New purchases total {_usd(total)} of your {_usd(request['total_budget'])} budget.")
        else:
            parts.append(f"New purchases total {_usd(total)}.")
        if owned:
            names = sorted({(i["wardrobe_item"]["name"]) for i in owned.values()})
            parts.append(f"I reused your {', '.join(names)} instead of buying new.")
        rec["message"] = " ".join(parts)
    else:
        rec["message"] = conflict["message"] + " What would you like me to prioritize?"
    return rec


# ----------------------------------------------------------------------------- plan
async def plan_shopping(raw_request: str, user_id: str, session_id: str, profile: dict | None = None,
                        wardrobe: list[dict] | None = None, bus=None, on_event=None) -> dict:
    bus = bus or LocalBus()
    events: list[dict] = []

    def emit(e):
        events.append(e)
        if on_event:
            on_event(e)

    if getattr(bus, "mode", "") == "local":
        emit(make_event(session_id, ORCH, "mode", "Running agents in-process (local mode, Fetch.ai network not used)."))
    emit(make_event(session_id, ORCH, "request_received", "Understanding your request…", "working"))
    parsed = parse_request(raw_request, session_id, user_id, wardrobe or [])
    request = parsed["request"]
    if profile:
        if not request.get("styles"):
            request["styles"] = list(profile.get("preferred_styles") or [])
        if not request.get("preferred_colors"):
            request["preferred_colors"] = list(profile.get("preferred_colors") or [])
        if not request.get("avoid"):
            request["avoid"] = list(profile.get("avoided_colors") or [])
    if request.get("per_outfit_budget") is None and profile and profile.get("default_budget_per_outfit") is not None:
        request["per_outfit_budget"] = profile["default_budget_per_outfit"]
        request["hard_constraints"], request["soft_preferences"] = derive_constraint_lists(request, request)
    wardrobe_all = list(wardrobe or []) + parsed["new_wardrobe_items"]
    log.info("plan inventory count=%d ids=%s categories=%s sources=%s", len(wardrobe_all),
             [w.get("id") for w in wardrobe_all], [w.get("category") for w in wardrobe_all],
             [w.get("source", "wardrobe") for w in wardrobe_all])

    if parsed["clarification"]:
        emit(make_event(session_id, ORCH, "request_parsed", parsed["clarification"], "failed"))
        rec = empty_final_recommendation(session_id, "needs_user_input", parsed["clarification"], request, events)
        return _result(rec, parsed["new_wardrobe_items"])

    summary = [f"{request['number_of_outfits']} outfits"]
    if request.get("location"):
        summary.append(f"for {request['location']}")
    if request.get("per_outfit_budget") is not None:
        summary.append(f"≤ {_usd(request['per_outfit_budget'])}/outfit")
    if request.get("total_budget") is not None:
        summary.append(f"≤ {_usd(request['total_budget'])} total")
    if request.get("styles"):
        summary.append("style: " + ", ".join(request["styles"]))
    if request.get("required_items"):
        summary.append("must include: " + ", ".join(r["item"] for r in request["required_items"]))
    if request.get("avoid"):
        summary.append("avoid: " + ", ".join(request["avoid"]))
    if request.get("owned_item_references"):
        summary.append("owned: " + ", ".join(request["owned_item_references"]))
    emit(make_event(session_id, ORCH, "request_parsed",
                    ("Parsed with LLM: " if parsed["used_llm"] else "Parsed: ") + "; ".join(summary)))
    for w in parsed["new_wardrobe_items"]:
        emit(make_event(session_id, ORCH, "memory",
                        f"Noted that you own {w['name']} ({'remembered' if w['memory_type'] == 'remembered' else 'temporary, expires in 30 days'})."))

    planner = TripPlanner(session_id, request, profile, wardrobe_all, bus, events, on_event=on_event)
    try:
        remaining = await planner.plan()
    except Exception as exc:  # agent failure: report honestly, never pretend success
        log.exception("planning failed")
        events.append(make_event(session_id, ORCH, "conflict", f"Agent workflow failed: {exc}", "failed"))
        rec = empty_final_recommendation(session_id, "failed", "Sorry — the shopping agents hit an error. Please try again.",
                                         request, events)
        return _result(rec, parsed["new_wardrobe_items"])

    conflict = _conflict(remaining, request, planner) if remaining else None
    rec = _finalize(planner, request, events, remaining, session_id, conflict)
    log.info("plan response session=%s wardrobe_reused=%s candidate_reused=%s purchases=%s", session_id,
             rec.get("wardrobe_reused_count"), rec.get("candidate_reused_count"), rec.get("unique_purchase_count"))
    if not planner.pool and any("live search failed" in e["message"] for e in events):
        # nothing could be retrieved at all: this is a service outage, not a constraint conflict
        rec.update(status="failed", message="I couldn't reach the product search service, so I can't build outfits "
                                            "right now. Please try again in a moment.")
        conflict = None
    events.append(make_event(session_id, ORCH, "plan_completed" if not remaining else "conflict", rec["message"],
                             "completed" if not remaining else "failed"))
    save_session(session_id, {"request": request, "profile": profile, "wardrobe": wardrobe_all,
                              "planner": planner.state(), "last_recommendation": rec})
    return _result(rec, parsed["new_wardrobe_items"], conflict)


# ----------------------------------------------------------------------------- modify
async def modify_shopping(modification: dict, profile: dict | None = None, wardrobe: list[dict] | None = None,
                          bus=None, previous_state: dict | None = None, on_event=None) -> dict:
    bus = bus or LocalBus()
    sid = modification["session_id"]
    events: list[dict] = []
    session = previous_state or load_session(sid)
    if not session:
        rec = empty_final_recommendation(sid, "failed", "I couldn't find that shopping session. Please start a new plan.")
        return _result(rec)

    request = copy.deepcopy(session["request"])
    profile = profile if profile is not None else session.get("profile")
    wardrobe_all = list(wardrobe) if wardrobe is not None else list(session.get("wardrobe") or [])
    known = {w["id"] for w in wardrobe_all}
    wardrobe_all += [w for w in session.get("wardrobe") or [] if w["id"] not in known]

    planner = TripPlanner(sid, request, profile, wardrobe_all, bus, events,
                          state=copy.deepcopy(session["planner"]), on_event=on_event)
    act = interpret_modification(modification["message"], modification.get("target_outfit_id"), planner.outfits)
    planner.ev("modification_parsed", _describe_actions(act), agent=ORCH)
    if not act["understood"]:
        rec = copy.deepcopy(session["last_recommendation"])
        rec["agent_events"] = events
        rec["message"] = ("I wasn't sure what to change. Try e.g. \"replace the skirt in outfit 3\", "
                          "\"make day 4 more elegant\" or \"my total budget is now $300\".")
        return _result(rec)

    new_wardrobe, profile_updates = [], None
    affected: set[str] = set(act["target_outfit_ids"])

    # 1) budgets
    if act["budget_changes"]:
        request.update(act["budget_changes"])
        request["hard_constraints"], request["soft_preferences"] = derive_constraint_lists(request, request)
        affected |= {o["id"] for o in planner.outfits}

    # 2) avoids -> rescore everything, replan outfits containing avoided items
    if act["add_avoid"]:
        request["avoid"] = sorted(set(request["avoid"]) | set(act["add_avoid"]))
        planner.scores = {}
        if act["remember"]:
            profile_updates = {"avoided_styles_add": act["add_avoid"]}
        await planner._style(list(planner.pool.values()) + planner.wardrobe,
                             sorted({planner.ctx_key(o) for o in planner.outfits}))
        for o in planner.outfits:
            for slot, p in o["picks"].items():
                s = p and planner.score(p["item"]["id"], planner.ctx_key(o))
                if p and s and s["excluded"]:
                    o["picks"][slot] = None
                    affected.add(o["id"])

    # 3) "I bought the skirt" -> becomes a wardrobe item, no longer a purchase
    for b in act["bought"]:
        hit = None
        for o in planner.outfits:
            if b["outfit_id"] and o["id"] != b["outfit_id"]:
                continue
            for p in o["picks"].values():
                if p and p["source"] == "product" and tx.matches_kind(p["item"], b["kind"]):
                    hit = p["item"]
                    break
            if hit:
                break
        if not hit:
            planner.ev("modification_parsed", f"Couldn't find a '{b['kind']}' in your plan to mark as bought.",
                       status="failed", agent=ORCH)
            continue
        w = make_wardrobe_item(modification["user_id"], hit["name"], hit["category"], hit.get("subcategory"),
                               hit["colors"], hit["tags"], act["remember"], hit["price"],
                               item_id=f"wardrobe_{hit['id']}")
        w["image_url"] = hit.get("image_url")
        new_wardrobe.append(w)
        planner.wardrobe.append(w)
        planner.scores[w["id"]] = dict(planner.scores.get(hit["id"], {}))
        for o in planner.outfits:
            for slot, p in o["picks"].items():
                if p and p["item"]["id"] == hit["id"]:
                    o["picks"][slot] = {"source": "wardrobe", "item": w, "required": p["required"], "locked": False}
                    affected.add(o["id"])
        planner.ev("memory", f"Marked {hit['name']} as owned — it no longer counts toward purchases.", agent=ORCH)

    # 4) targeted outfit edits
    for oid in act["target_outfit_ids"] or ([o["id"] for o in planner.outfits] if (act["style_modifiers"] and not act["budget_changes"]) else []):
        o = planner.outfit(oid)
        affected.add(oid)
        if act["style_modifiers"]:
            o["style_modifiers"] = sorted(set(o.get("style_modifiers") or []) | set(act["style_modifiers"]))
        for slot in o["template"]:
            if o["picks"].get(slot) and tx.kind_category(slot) and slot in act["keep_categories"]:
                o["picks"][slot]["locked"] = True
        slots = list(o["template"]) if act["replace_all"] else [s for s in act["replace_categories"] if s in o["template"]]
        slots = [s for s in slots if s not in act["keep_categories"]]
        if not slots and act["replace_categories"]:
            planner.ev("modification_parsed", f"{oid} has no {', '.join(act['replace_categories'])} to replace.",
                       oid, "failed", ORCH)
        await planner._style(list(planner.pool.values()) + planner.wardrobe, [planner.ctx_key(o)], oid)
        limit = request.get("per_outfit_budget")
        for slot in slots:
            kept = sum(p["item"]["price"] for s, p in o["picks"].items()
                       if p and s not in slots and p["source"] == "product")
            cur = o["picks"].get(slot)
            cap = (limit - kept) if limit is not None else (cur["item"].get("price", 50) * 2 if cur else 100)
            if act.get("replacement_budget") is not None:
                cap = min(cap, act["replacement_budget"])
            if act["cheaper"] and cur and cur["source"] == "product":
                cap = min(cap, round(cur["item"]["price"] * 0.7, 2))
            reason = "per your request" + (f" ({', '.join(act['style_modifiers'])})" if act["style_modifiers"] else "")
            await planner.replace_slot(o, slot, round(max(cap, 1), 2), why=reason)

    # 5) fill holes left by avoid changes, then check + replan only affected outfits
    for oid in affected:
        o = planner.outfit(oid)
        if any(o["picks"].get(s) is None for s in o["template"]):
            planner._build_outfit(o, announce=False)
    remaining = await planner.check_and_replan(sorted(affected) or [o["id"] for o in planner.outfits])
    for o in planner.outfits:
        for p in o["picks"].values():
            if p:
                p["locked"] = False

    conflict = _conflict(remaining, request, planner) if remaining else None
    changed = ", ".join(a.replace("_", " ") for a in sorted(affected)) or "your plan"
    rec = _finalize(planner, request, events, remaining, sid, conflict, intro=f"Updated {changed}.")
    events.append(make_event(sid, ORCH, "plan_completed" if not remaining else "conflict", rec["message"],
                             "completed" if not remaining else "failed"))
    save_session(sid, {"request": request, "profile": profile, "wardrobe": planner.wardrobe,
                       "planner": planner.state(), "last_recommendation": rec})
    return _result(rec, new_wardrobe, conflict, profile_updates)


def _describe_actions(a: dict) -> str:
    bits = []
    if a["target_outfit_ids"]:
        bits.append("target " + ", ".join(a["target_outfit_ids"]))
    if a["keep_categories"]:
        bits.append("keep " + ", ".join(a["keep_categories"]))
    if a["replace_all"]:
        bits.append("replan whole outfit")
    elif a["replace_categories"]:
        bits.append("replace " + ", ".join(a["replace_categories"]))
    if a["style_modifiers"]:
        bits.append("make it more " + ", ".join(a["style_modifiers"]))
    if a["cheaper"]:
        bits.append("cheaper")
    for k, v in a["budget_changes"].items():
        bits.append(f"{k.replace('_', ' ')} → {_usd(v)}")
    if a["add_avoid"]:
        bits.append("avoid " + ", ".join(a["add_avoid"]))
    for b in a["bought"]:
        bits.append(f"you own the {b['kind']}")
    return "Understood: " + ("; ".join(bits) if bits else "nothing actionable")
