"""AgentBus: how the planner talks to the specialist agents.

LocalBus  -> calls agent logic in-process (tests, and a fallback if the Fetch agents are down).
FetchBus  -> real uAgents message passing (agents/fetch/orchestrator.py).
Both expose the same three async methods, each returning (result, events).
"""
from __future__ import annotations

import asyncio

from agents.core.agent_logic import budget_agent_handle, search_agent_handle, style_agent_handle


class AgentUnavailable(RuntimeError):
    pass


class LocalBus:
    mode = "local"

    async def search(self, session_id, search_request, reason="", outfit_id=None):
        return await asyncio.to_thread(search_agent_handle, session_id, search_request, reason, outfit_id)

    async def style(self, session_id, request, profile, contexts, products, outfit_id=None):
        return style_agent_handle(session_id, request, profile, contexts, products, outfit_id)

    async def check(self, session_id, request, outfits, check_outfit_ids=None):
        return budget_agent_handle(session_id, request, outfits, check_outfit_ids)
