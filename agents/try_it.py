"""Interactive tester: type normal sentences, they go through the REAL agent API over HTTP.

    Terminal 1:  python -m agents.fetch.run_bureau
    Terminal 2:  python3 -m agents.try_it

First message -> POST /plan. Follow-ups ("make day 2 more elegant", "I hate outfit 3",
"my total budget is now $300") -> POST /modify on the same session. Type "new" for a new plan,
"json" to dump the last raw response, "quit" to exit.

After each answer it prints exactly which calls happened:
  - HTTP call to the orchestrator agent (status code, time)
  - which agents produced output (search / style / budget)
  - whether the LLM API was used for parsing, or the rule-based fallback
  - whether products came from the live product service or the fallback catalog
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("AGENTS_URL", f"http://localhost:{os.environ.get('AGENTS_PORT', '8001')}")
COLORS = {"orchestrator": "\033[95m", "planner": "\033[94m", "search_agent": "\033[96m",
          "style_agent": "\033[92m", "budget_agent": "\033[93m"}
RESET, BOLD, RED, GREEN = "\033[0m", "\033[1m", "\033[91m", "\033[92m"


def post(path: str, body: dict) -> tuple[int, dict, float]:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.status, json.loads(r.read().decode()), time.time() - t0


def health() -> dict | None:
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def show(status: int, data: dict, secs: float, path: str) -> None:
    rec = data["final_recommendation"]
    events = rec["agent_events"]
    print(f"\n{BOLD}--- Agent trace ---{RESET}")
    for e in events:
        c = COLORS.get(e["agent"], "")
        mark = RED if e["status"] == "failed" else ""
        print(f"  {c}[{e['agent']:<12}]{RESET} {mark}{e['type']:<20}{RESET} {e['message']}")

    print(f"\n{BOLD}--- Result ---{RESET}")
    print(f"  {rec['message']}")
    for o in rec["outfits"]:
        names = [((i["product"] or i["wardrobe_item"])["name"]
                  + (f" ${i['product']['price']:.2f}" if i["product"] else " (owned)")) for i in o["items"]]
        ok = f"{GREEN}OK{RESET}" if o["constraints_satisfied"] else f"{RED}!!{RESET}"
        print(f"  [{ok}] Day {o['day']} {o['title']:<26} match {o['match_score']:>3}  "
              f"${o['new_purchase_cost']:>6.2f}  {' + '.join(names)}")
    if data.get("conflict"):
        print(f"  {RED}Needs your input:{RESET} " + " | ".join(data["conflict"]["options"]))
    if rec["outfits"]:
        print(f"  Total new purchases: ${rec['total_new_purchase_cost']:.2f}"
              + (f" of ${rec['total_budget']:.2f}" if rec.get("total_budget") is not None else ""))

    agents = sorted({e["agent"] for e in events})
    parsed = next((e["message"] for e in events if e["type"] == "request_parsed"), "")
    searches = [e["message"] for e in events if e["type"] == "search_completed"]
    live = sum("live product service" in m for m in searches)
    local_mode = any(e["type"] == "mode" for e in events)
    print(f"\n{BOLD}--- API calls made ---{RESET}")
    print(f"  HTTP POST {BASE}{path} -> {status} in {secs:.1f}s")
    print(f"  Agents that produced output: {', '.join(agents)}")
    print(f"  Fetch.ai agent messaging: {RED + 'NO (local mode)' + RESET if local_mode else GREEN + 'yes' + RESET}")
    if path == "/plan":
        llm = parsed.startswith("Parsed with LLM")
        print(f"  LLM API for parsing: {GREEN + 'yes' + RESET if llm else 'no (rule-based parser; add a key to .env)'}")
    print(f"  Product searches: {len(searches)} "
          f"({live} live product service, {len(searches) - live} fallback catalog)")


def main() -> None:
    h = health()
    if not h:
        print(f"{RED}Can't reach the agents at {BASE}.{RESET} Start them first in another terminal:\n"
              "  source .venv/bin/activate && python -m agents.fetch.run_bureau")
        sys.exit(1)
    print(f"{GREEN}Connected to agents at {BASE}{RESET}")
    for name, addr in h["agents"].items():
        print(f"  {name:<13} {addr}")
    print("\nType a shopping request. Follow-ups modify the same plan. Commands: new, json, quit\n")

    session, user, last = None, "user_" + uuid.uuid4().hex[:6], None
    while True:
        try:
            text = input(f"{BOLD}you>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            break
        if text.lower() == "new":
            session = None
            print("Starting a new plan.")
            continue
        if text.lower() == "json":
            print(json.dumps(last, indent=2) if last else "No response yet.")
            continue
        try:
            if session is None:
                session = "try_" + uuid.uuid4().hex[:8]
                path, body = "/plan", {"raw_request": text, "user_id": user, "session_id": session}
            else:
                path, body = "/modify", {"session_id": session, "user_id": user, "message": text}
            print("  ...agents working...")
            status, data, secs = post(path, body)
            last = data
            show(status, data, secs, path)
            if data["final_recommendation"]["status"] == "failed" and path == "/plan":
                session = None
        except urllib.error.HTTPError as e:
            print(f"{RED}HTTP {e.code}:{RESET} {e.read().decode()[:500]}")
        except (urllib.error.URLError, OSError) as e:
            print(f"{RED}Request failed:{RESET} {e}. Are the agents still running?")
        print()


if __name__ == "__main__":
    main()
