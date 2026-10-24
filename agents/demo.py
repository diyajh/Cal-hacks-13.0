"""Run the canonical demo locally (no uagents/network needed) and print the agent trace.

    python -m agents.demo                     # plan + modification, prints events
    python -m agents.demo --write-examples    # also writes shared/examples/agents_*.json for teammates
    python -m agents.demo "your own request here"
"""
from __future__ import annotations

import asyncio
import json
import sys

from agents import config
from agents.core.engine import modify_shopping, plan_shopping
from agents.core.parser import parse_request

CANONICAL = ("I'm going to San Diego for five days. I need five outfits. Each outfit should be under $50 and my "
             "total budget is $500. I want a beachy neutral aesthetic. One outfit needs a crochet top and skirt. "
             "I like beige and white. I don't like neon colors. I already own white sneakers. Remember that I own them.")
MODIFY = "Keep the top in outfit three but replace the skirt and make it more elegant."


def show(result: dict) -> None:
    rec = result["final_recommendation"]
    for e in rec["agent_events"]:
        print(f"  [{e['agent']:<12}] {e['type']:<20} {e['message']}")
    print(f"\n  STATUS: {rec['status']}  |  new purchases ${rec['total_new_purchase_cost']:.2f}"
          f"  |  all constraints satisfied: {rec['all_constraints_satisfied']}")
    print(f"  {rec['message']}\n")
    for o in rec["outfits"]:
        names = [(i["product"] or i["wardrobe_item"])["name"] for i in o["items"]]
        print(f"  {o['id']}  Day {o['day']}  {o['title']:<26} score {o['match_score']:>3}  ${o['new_purchase_cost']:>6.2f}  {names}")
    if result["conflict"]:
        print("\n  CONFLICT:", json.dumps(result["conflict"], indent=2))


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write-examples" in sys.argv
    text = " ".join(args) or CANONICAL
    sid = "session_demo"

    print("=" * 100, "\nPLAN:", text, "\n" + "=" * 100)
    plan = await plan_shopping(text, "user_123", sid)
    show(plan)

    if not args:
        print("=" * 100, "\nMODIFY:", MODIFY, "\n" + "=" * 100)
        mod = await modify_shopping({"session_id": sid, "user_id": "user_123", "message": MODIFY,
                                     "target_outfit_id": None})
        show(mod)
        if write:
            out = config.REPO_ROOT / "shared" / "examples"
            out.mkdir(parents=True, exist_ok=True)
            (out / "agents_shopping_request.json").write_text(
                json.dumps(parse_request(text, sid, "user_123", use_llm=False)["request"], indent=2))
            (out / "agents_final_recommendation.json").write_text(json.dumps(plan["final_recommendation"], indent=2))
            (out / "agents_modified_recommendation.json").write_text(json.dumps(mod["final_recommendation"], indent=2))
            (out / "agents_plan_result.json").write_text(json.dumps(plan, indent=2))
            print(f"wrote examples to {out}")


if __name__ == "__main__":
    asyncio.run(main())
