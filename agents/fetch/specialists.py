"""The three specialist uAgents: Search, Style, Budget/Constraint.

Each one receives a message, does its job via agents.core.agent_logic, and replies to the
sender with its result plus the AgentEvents it generated (so the UI sees real agent activity).
"""
from __future__ import annotations

import asyncio

from uagents import Context

from agents.fetch.factory import make_agent
from agents.core.agent_logic import budget_agent_handle, search_agent_handle, style_agent_handle
from agents.fetch.messages import (ConstraintCheckMsg, ConstraintResultMsg, SearchRequestMsg, SearchResponseMsg,
                                   StyleRequestMsg, StyleResponseMsg)

search_agent = make_agent("search_agent", "search",
                          "Finds real products for a shopping plan (category, colors, max price) via the product service.")
style_agent = make_agent("style_agent", "style",
                         "Scores products 0-100 for style, color, occasion and preference fit; excludes avoided colors/styles.")
budget_agent = make_agent("budget_agent", "budget",
                          "Checks hard constraints: per-outfit budget, trip budget (reused items counted once), "
                          "required items, outfit count and completeness.")


@search_agent.on_message(model=SearchRequestMsg, replies=SearchResponseMsg)
async def on_search(ctx: Context, sender: str, msg: SearchRequestMsg):
    ctx.logger.info(f"search: {msg.search_request.get('query')} (max {msg.search_request.get('max_price')})")
    # product search does blocking HTTP -> run off the event loop
    products, events = await asyncio.to_thread(
        search_agent_handle, msg.session_id, msg.search_request, msg.reason, msg.outfit_id)
    await ctx.send(sender, SearchResponseMsg(session_id=msg.session_id, request_id=msg.request_id, products=products, events=events))


@style_agent.on_message(model=StyleRequestMsg, replies=StyleResponseMsg)
async def on_style(ctx: Context, sender: str, msg: StyleRequestMsg):
    ctx.logger.info(f"style: scoring {len(msg.products)} items x {len(msg.contexts)} contexts")
    scores, events = style_agent_handle(msg.session_id, msg.request, msg.profile, msg.contexts,
                                        msg.products, msg.outfit_id)
    await ctx.send(sender, StyleResponseMsg(session_id=msg.session_id, request_id=msg.request_id, scores=scores, events=events))


@budget_agent.on_message(model=ConstraintCheckMsg, replies=ConstraintResultMsg)
async def on_check(ctx: Context, sender: str, msg: ConstraintCheckMsg):
    ctx.logger.info(f"budget: checking {len(msg.outfits)} outfits")
    violations, events = budget_agent_handle(msg.session_id, msg.request, msg.outfits, msg.check_outfit_ids)
    await ctx.send(sender, ConstraintResultMsg(session_id=msg.session_id, request_id=msg.request_id, violations=violations, events=events))
