"""Run all four agents in one process.

    python -m agents.fetch.run_bureau          (from the repo root)

REST API for FastAPI is served on http://localhost:$AGENTS_PORT (default 8001):
    POST /plan, POST /modify, GET /health
"""
from __future__ import annotations

from uagents import Bureau

from agents import config
from agents.fetch.orchestrator import orchestrator
from agents.fetch.specialists import budget_agent, search_agent, style_agent


def main() -> None:
    bureau = Bureau(port=config.ORCHESTRATOR_PORT)
    for agent in (orchestrator, search_agent, style_agent, budget_agent):
        bureau.add(agent)
    print(f"Shopping agents running. REST: http://localhost:{config.ORCHESTRATOR_PORT}/plan  /modify  /health")
    bureau.run()


if __name__ == "__main__":
    main()
