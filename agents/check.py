"""Verify each piece of the agent system yourself, one at a time.

Run from the repo root (no installs needed — uses the local bus + mock catalog):

  python -m agents.check parse  "5 days in San Diego, 5 outfits under $50 each, I own white sneakers"
  python -m agents.check search "crochet top" --category top --max 25
  python -m agents.check score  "Beige Crochet Tank" --occasion beach
  python -m agents.check plan                          # full canonical run, events grouped by agent
  python -m agents.check plan --agent budget_agent     # only one agent's output
  python -m agents.check modify "Keep the top in outfit three but replace the skirt and make it more elegant."
  python -m agents.check conflict                      # impossible request -> needs_user_input
  python -m agents.check chat "5 days in San Diego, 5 outfits under $50 each"   # reply an ASI:One user would see
  python -m agents.check chat "make day 2 more elegant" --user me                # follow-up in same chat
  python -m agents.check llm "Heading to Tulum, 3 looks, nothing over 40 bucks"   # is the LLM path working?
  python -m agents.check live "beachy crochet top" --category top --max 50       # ONE real call to Person 2
  python -m agents.check cache-clear                    # forget cached live searches
  python -m agents.check all                           # every check with PASS/FAIL
"""
from __future__ import annotations

import argparse
import asyncio
import json

from agents.core.agent_logic import budget_agent_handle, search_agent_handle
from agents.core.engine import modify_shopping, plan_shopping
from agents.core.parser import parse_request
from agents.core.scoring import build_context, score_item
from agents.products.client import load_fallback_catalog, make_search_request

CANONICAL = ("I'm going to San Diego for five days. I need five outfits. Each outfit should be under $50 and my "
             "total budget is $500. I want a beachy neutral aesthetic. One outfit needs a crochet top and skirt. "
             "I like beige and white. I don't like neon colors. I already own white sneakers. Remember that I own them.")
SESSION = "session_check"


def hdr(t):
    print("\n" + "=" * 90 + f"\n{t}\n" + "=" * 90)


def show_outfits(rec):
    for o in rec["outfits"]:
        names = [((i["product"] or i["wardrobe_item"])["name"]
                  + ("" if i["source_type"] == "product" else " (owned)")) for i in o["items"]]
        ok = "OK " if o["constraints_satisfied"] else "BAD"
        print(f"  [{ok}] {o['id']}  Day {o['day']} {o['occasion']:<11} score {o['match_score']:>3}  "
              f"${o['new_purchase_cost']:>6.2f}  {' + '.join(names)}")
    print(f"\n  status={rec['status']}  total_new_purchase_cost=${rec['total_new_purchase_cost']}  "
          f"all_constraints_satisfied={rec['all_constraints_satisfied']}\n  message: {rec['message']}")


def cmd_parse(text):
    hdr("INPUT (natural language)")
    print(" ", text)
    out = parse_request(text, SESSION, "user_123", use_llm=False)
    hdr("OUTPUT ShoppingRequest")
    print(json.dumps(out["request"], indent=2))
    hdr("OUTPUT new wardrobe items for Person 2 to save")
    print(json.dumps(out["new_wardrobe_items"], indent=2))
    return out


def cmd_search(query, category, max_price):
    req = make_search_request(query, category, [], [], max_price, 20)
    hdr("SEARCH AGENT — INPUT ProductSearchRequest")
    print(json.dumps(req, indent=2))
    products, events = search_agent_handle(SESSION, req, "manual check")
    hdr(f"SEARCH AGENT — OUTPUT {len(products)} products")
    for p in products:
        print(f"  ${p['price']:>6.2f}  {p['category']:<8} {p['name']}  colors={p['colors']}")
    for e in events:
        print(f"  event: {e['message']}")
    return products


def cmd_score(name, occasion):
    req = parse_request(CANONICAL, SESSION, "user_123", use_llm=False)["request"]
    matches = [p for p in load_fallback_catalog() if name.lower() in p["name"].lower()]
    hdr(f"STYLE AGENT — scoring against: styles={req['styles']} colors={req['preferred_colors']} "
        f"avoid={req['avoid']} occasion={occasion}")
    for p in matches:
        s = score_item(p, build_context(req, None, occasion))
        print(f"  {p['name']}  tags={p['tags']}  colors={p['colors']}")
        print(f"    -> {json.dumps(s)}")
    if not matches:
        print("  no catalog product matches that name")


def cmd_plan(agent_filter=None, text=CANONICAL):
    res = asyncio.run(plan_shopping(text, "user_123", SESSION))
    rec = res["final_recommendation"]
    hdr("AGENT TRACE" + (f" (only {agent_filter})" if agent_filter else ""))
    for e in rec["agent_events"]:
        if agent_filter and e["agent"] != agent_filter:
            continue
        print(f"  [{e['agent']:<12}] {e['type']:<20} {e['message']}")
    hdr("FINAL OUTFITS")
    show_outfits(rec)
    return res


def cmd_modify(message):
    asyncio.run(plan_shopping(CANONICAL, "user_123", SESSION))  # make sure a session exists
    from agents.core.engine import load_session
    before = load_session(SESSION)["last_recommendation"]
    hdr("BEFORE")
    show_outfits(before)
    res = asyncio.run(modify_shopping({"session_id": SESSION, "user_id": "user_123", "message": message,
                                       "target_outfit_id": None}))
    rec = res["final_recommendation"]
    hdr(f"MODIFICATION: {message}")
    for e in rec["agent_events"]:
        print(f"  [{e['agent']:<12}] {e['type']:<20} {e['message']}")
    hdr("AFTER")
    show_outfits(rec)
    b = {o["id"]: [i["id"] for i in o["items"]] for o in before["outfits"]}
    a = {o["id"]: [i["id"] for i in o["items"]] for o in rec["outfits"]}
    print("\n  changed outfits:", [k for k in a if a[k] != b.get(k)] or "none")
    return before, rec


def cmd_conflict():
    res = cmd_plan(text="2 outfits for brunch, each outfit under $15, must include a satin dress")
    hdr("CONFLICT (returned to user)")
    print(json.dumps(res["conflict"], indent=2))
    return res


def cmd_chat(text, user):
    from agents.core.bus import LocalBus
    from agents.fetch.chat import handle_chat_text  # works without uagents installed
    hdr(f"ASI:One user '{user}' says: {text}")
    print(asyncio.run(handle_chat_text(text, f"agent1q-local-{user}", LocalBus())))


def cmd_llm(text):
    from agents import config
    from agents.core.llm import LAST, llm_available
    hdr("LLM PARSER CHECK")
    if not llm_available():
        print("  No ANTHROPIC_API_KEY / OPENAI_API_KEY in .env -> rule-based parser only.")
        return
    out = parse_request(text, SESSION, "user_123", use_llm=True)
    print(f"  provider={LAST['provider']}  model={LAST['model']}  used_llm={out['used_llm']}")
    if not out["used_llm"]:
        print(f"  LLM FAILED -> rules fallback. Error: {LAST['error']}")
        print("  Fix: check the key, credits, or set LLM_MODEL in .env to a model your key can use.")
    print(json.dumps({k: out["request"][k] for k in ("location", "duration_days", "number_of_outfits",
          "per_outfit_budget", "total_budget", "styles", "preferred_colors", "avoid", "required_items",
          "occasions")}, indent=2))


def cmd_live(query, category, max_price):
    from agents import config
    from agents.products.client import SOURCE_LABELS, search_products
    if not config.PRODUCT_SEARCH_URL:
        print("PRODUCT_SEARCH_URL is not set in .env")
        return
    req = make_search_request(query, category, [], [], max_price, 20)
    hdr(f"ONE live search -> {config.PRODUCT_SEARCH_URL}")
    print(json.dumps(req))
    products, source, stats = search_products(req)
    print(f"\n  source: {SOURCE_LABELS.get(source, source)}   stats: {stats}")
    for p in products[:20]:
        print(f"  ${p['price']:>7.2f}  {p['category']:<7} {str(p['retailer'])[:14]:<14} {p['name'][:60]}"
              f"  url={'yes' if p['product_url'] else 'NO'} img={'yes' if p['image_url'] else 'NO'} src={p['source']}")


def cmd_all():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    req = parse_request(CANONICAL, SESSION, "user_123", use_llm=False)["request"]
    check("parse: location/days/outfits", (req["location"], req["duration_days"], req["number_of_outfits"]) == ("San Diego", 5, 5))
    check("parse: budgets 50/500", (req["per_outfit_budget"], req["total_budget"]) == (50, 500))
    check("parse: required crochet top + skirt", [r["item"] for r in req["required_items"]] == ["crochet top", "skirt"])
    check("parse: owns white sneakers", req["owned_item_references"] == ["wardrobe_white_sneakers"])
    check("parse: avoid neon", req["avoid"] == ["neon"])

    prods, _ = search_agent_handle(SESSION, make_search_request("sandals", "shoes", [], [], 13, 20))
    check("search: respects max_price", prods and all(p["price"] <= 13 for p in prods))

    tee = next(p for p in load_fallback_catalog() if "Neon" in p["name"])
    check("style: neon item excluded", score_item(tee, build_context(req, None, "beach"))["excluded"])

    over = {"id": "outfit_x", "title": "Test", "items": [
        {"source_type": "product", "purchase_required": True, "wardrobe_item": None,
         "product": {"id": "a", "name": "A", "price": 40.0, "category": "dress", "colors": [], "tags": []}},
        {"source_type": "product", "purchase_required": True, "wardrobe_item": None,
         "product": {"id": "b", "name": "B", "price": 20.0, "category": "shoes", "colors": [], "tags": []}}]}
    v, _ = budget_agent_handle(SESSION, {**req, "number_of_outfits": 1, "required_items": []}, [over])
    check("budget: $60 outfit rejected vs $50", any(x["constraint"] == "per_outfit_budget" for x in v))

    res = asyncio.run(plan_shopping(CANONICAL, "user_123", SESSION))
    rec = res["final_recommendation"]
    types = [e["type"] for e in rec["agent_events"]]
    agents = {e["agent"] for e in rec["agent_events"]}
    check("plan: status completed, 5 outfits", rec["status"] == "completed" and len(rec["outfits"]) == 5)
    check("plan: every outfit <= $50", all(o["new_purchase_cost"] <= 50 for o in rec["outfits"]))
    check("plan: trip total <= $500", rec["total_new_purchase_cost"] <= 500)
    check("plan: replanning happened", "constraint_violation" in types and "replacement_found" in types)
    check("plan: all 3 specialist agents emitted events", {"search_agent", "style_agent", "budget_agent"} <= agents)
    check("plan: owned sneakers reused", any(i["wardrobe_item"]["id"] == "wardrobe_white_sneakers" for i in rec["owned_items_used"]))

    before = rec
    mod = asyncio.run(modify_shopping({"session_id": SESSION, "user_id": "user_123",
                                       "message": "Keep the top in outfit three but replace the skirt and make it more elegant.",
                                       "target_outfit_id": None}))["final_recommendation"]
    b = {o["id"]: [i["id"] for i in o["items"]] for o in before["outfits"]}
    a = {o["id"]: [i["id"] for i in o["items"]] for o in mod["outfits"]}
    check("modify: only outfit_3 changed", [k for k in a if a[k] != b[k]] == ["outfit_3"])

    conf = asyncio.run(plan_shopping("2 outfits for brunch, each outfit under $15, must include a satin dress", "u", "s_c"))
    check("conflict: needs_user_input + options", conf["final_recommendation"]["status"] == "needs_user_input" and conf["conflict"]["options"])

    hdr("RESULTS")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n  {sum(ok for _, ok in results)}/{len(results)} passed")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse"); p.add_argument("text", nargs="?", default=CANONICAL)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--category"); p.add_argument("--max", type=float)
    p = sub.add_parser("score"); p.add_argument("name"); p.add_argument("--occasion", default="beach")
    p = sub.add_parser("plan"); p.add_argument("--agent"); p.add_argument("--text", default=CANONICAL)
    p = sub.add_parser("modify"); p.add_argument("message")
    sub.add_parser("conflict")
    p = sub.add_parser("llm"); p.add_argument("text", nargs="?", default="Heading to Tulum for a long weekend, need 3 looks, nothing over 40 bucks each, into boho stuff but hate anything yellow")
    p = sub.add_parser("live"); p.add_argument("query"); p.add_argument("--category"); p.add_argument("--max", type=float)
    sub.add_parser("cache-clear")
    p = sub.add_parser("chat"); p.add_argument("text"); p.add_argument("--user", default="demo")
    sub.add_parser("all")
    a = ap.parse_args()
    if a.cmd == "parse":
        cmd_parse(a.text)
    elif a.cmd == "search":
        cmd_search(a.query, a.category, a.max)
    elif a.cmd == "score":
        cmd_score(a.name, a.occasion)
    elif a.cmd == "plan":
        cmd_plan(a.agent, a.text)
    elif a.cmd == "modify":
        cmd_modify(a.message)
    elif a.cmd == "llm":
        cmd_llm(a.text)
    elif a.cmd == "live":
        cmd_live(a.query, a.category, a.max)
    elif a.cmd == "cache-clear":
        from agents.products.client import clear_cache
        print(f"removed {clear_cache()} cached searches")
    elif a.cmd == "chat":
        cmd_chat(a.text, a.user)
    elif a.cmd == "conflict":
        cmd_conflict()
    else:
        cmd_all()


if __name__ == "__main__":
    main()
