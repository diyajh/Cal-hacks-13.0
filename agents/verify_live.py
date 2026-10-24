"""ONE end-to-end check of live products through the real Fetch agents, with a report for Person 2.

Prereqs: Person 2's FastAPI on :8000, PRODUCT_SEARCH_URL set in .env, bureau running:
    python -m agents.fetch.run_bureau
Then:
    python3 -m agents.verify_live

Apify cost: ~8-12 live searches the FIRST time; reruns are served from the 24h search cache (free).
Steps:
  A. Search Agent's product client -> Person 2 /products/search with Person 2's sample request
  B. POST :8001/plan  (orchestrator -> search/style/budget agents -> planner) San Diego request
  C. POST :8001/modify "make day 3 more elegant"  (forces a live replacement search by the Search Agent)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

from agents import config
from agents.products.client import SOURCE_LABELS, search_products

AGENTS = os.environ.get("AGENTS_URL", f"http://localhost:{config.ORCHESTRATOR_PORT}")
PLAN_TEXT = ("I'm going to San Diego for five days. I need five outfits. Each outfit should be under $50 and my total "
             "budget is $500. I want a beachy neutral aesthetic. One outfit needs a crochet top and skirt. "
             "I don't like neon colors. I already own white sneakers.")
P2_SAMPLE = {"query": "beige crochet top women", "category": "top", "colors": ["beige", "white"],
             "tags": ["beachy", "coastal"], "max_price": 50, "limit": 20}

report: list[str] = []


def say(line=""):
    print(line)
    report.append(line)


def post(path, body, timeout=600):
    req = urllib.request.Request(AGENTS + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def analyze(rec: dict, label: str):
    ev = rec["agent_events"]
    searches = [e for e in ev if e["agent"] == "search_agent" and e["type"] == "search_completed"]
    started = [e for e in ev if e["agent"] == "search_agent" and e["type"] == "search_started"]
    repl = [e for e in started if "replacement search" in e["message"]]
    live = [e for e in searches if "live product service" in e["message"] and "(cached)" not in e["message"]]
    cached = [e for e in searches if "(cached)" in e["message"]]
    failed = [e for e in searches if "live search failed" in e["message"]]
    products = [i["product"] for o in rec["outfits"] for i in o["items"] if i["product"]]
    sources = sorted({str(p.get("source")) for p in products})
    shops = sorted({p["retailer"] for p in products if p.get("retailer")})
    say(f"[{label}] status={rec['status']}  outfits={len(rec['outfits'])}  "
        f"all_constraints_satisfied={rec['all_constraints_satisfied']}  new purchases=${rec['total_new_purchase_cost']}")
    say(f"   search agent: {len(searches)} searches ({len(live)} live, {len(cached)} cached, {len(failed)} failed); "
        f"{len(repl)} replacement searches during replanning")
    say(f"   budget agent rejections: {sum(1 for e in ev if e['type'] == 'constraint_violation')}; "
        f"replacements found: {sum(1 for e in ev if e['type'] == 'replacement_found')}")
    say(f"   products in final plan: {len(products)}  sources={sources}  retailers={shops}")
    say(f"   with product_url: {sum(1 for p in products if p.get('product_url'))}/{len(products)}   "
        f"with image_url: {sum(1 for p in products if p.get('image_url'))}/{len(products)}")
    for o in rec["outfits"]:
        names = [((i["product"] or i["wardrobe_item"])["name"][:38]
                  + (f" ${i['product']['price']:.2f} @{i['product'].get('retailer')}" if i["product"] else " (owned)"))
                 for i in o["items"]]
        say(f"   {o['id']} ${o['new_purchase_cost']:.2f} {'OK' if o['constraints_satisfied'] else '!!'}: " + " | ".join(names))
    for e in failed[:3]:
        say(f"   FAILED SEARCH: {e['message'][:200]}")
    return products


def main():
    if not config.PRODUCT_SEARCH_URL:
        sys.exit("PRODUCT_SEARCH_URL is not set in .env (expected http://localhost:8000/products/search)")

    say("=" * 30 + " A. Direct product search (Person 2 sample request) " + "=" * 30)
    say(f"POST {config.PRODUCT_SEARCH_URL}  {json.dumps(P2_SAMPLE)}")
    products, source, stats = search_products(P2_SAMPLE)
    say(f"   source: {SOURCE_LABELS.get(source, source)}")
    say(f"   received={stats.get('received')}  kept={stats.get('kept')}  invalid={stats.get('invalid')}  "
        f"unavailable={stats.get('unavailable')}  over_max_price={stats.get('over_max_price')}  "
        f"wrong_category={stats.get('wrong_category')}")
    for s in stats.get("rejected_samples", []):
        say(f"   REJECTED: {s}")
    if stats.get("error"):
        say(f"   ERROR: {stats['error']}")
    for p in products[:5]:
        say(f"   ${p['price']:.2f} [{p['category']}] {p['name'][:55]} @{p['retailer']} src={p['source']}")

    try:
        with urllib.request.urlopen(AGENTS + "/health", timeout=5) as r:
            json.loads(r.read().decode())
    except (urllib.error.URLError, OSError):
        sys.exit(f"\nAgents not reachable at {AGENTS}. Start: python -m agents.fetch.run_bureau")

    sid = "verify_" + uuid.uuid4().hex[:6]
    say("\n" + "=" * 30 + " B. Full plan through Fetch agents (POST :8001/plan) " + "=" * 30)
    print("   ...running (live Apify searches can take a few minutes the first time)...")
    plan = post("/plan", {"raw_request": PLAN_TEXT, "user_id": "verify_user", "session_id": sid})
    rec = plan["final_recommendation"]
    parsed = next((e["message"] for e in rec["agent_events"] if e["type"] == "request_parsed"), "")
    say(f"   parser: {'LLM' if parsed.startswith('Parsed with LLM') else 'rule-based (no LLM key / LLM failed)'}")
    plan_products = analyze(rec, "plan")
    if plan.get("conflict"):
        say(f"   conflict: {json.dumps(plan['conflict'])}")

    say("\n" + "=" * 30 + " C. Modification forcing a live replacement search (POST :8001/modify) " + "=" * 30)
    mod = post("/modify", {"session_id": sid, "user_id": "verify_user", "message": "make day 3 more elegant"})
    analyze(mod["final_recommendation"], "modify")

    say("\n" + "=" * 30 + " VERDICT " + "=" * 30)
    live_in_plan = [p for p in plan_products if p.get("source") == "apify"]
    other = [p for p in plan_products if p.get("source") != "apify"]
    say(f"   Live Apify products in final recommendation: {'YES' if live_in_plan else 'NO'} "
        f"({len(live_in_plan)} of {len(plan_products)} purchasable items)")
    if other:
        say(f"   Non-apify items in plan: {sorted({str(p.get('source')) for p in other})}")
    say(f"   Category validation drops in sample search: {stats.get('wrong_category', 0)} wrong_category, "
        f"{stats.get('invalid', 0)} invalid")

    out = config.AGENTS_DIR / ".cache" / "verify_report.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report))
    print(f"\nReport saved to {out} (paste it to Person 2).")


if __name__ == "__main__":
    main()
