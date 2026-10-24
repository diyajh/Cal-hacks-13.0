"""Orchestrator uAgent.

Exposes REST endpoints for FastAPI (Person 2):
    POST /plan    PlanRestRequest   -> AgentRestResponse
    POST /modify  ModifyRestRequest -> AgentRestResponse
    GET  /health                    -> HealthResponse

Internally the planner talks to the specialist agents through FetchBus, which sends real
uAgents messages for every search / style evaluation / constraint check. Replies are matched
to requests by request_id (works on old and new uagents; no ctx.send_and_receive needed).
"""
from __future__ import annotations

import asyncio
import uuid

from uagents import Agent, Context

from agents import config
from agents.core.bus import AgentUnavailable
from agents.core.engine import modify_shopping, plan_shopping
from agents.fetch.messages import (AgentRestResponse, ConstraintCheckMsg, ConstraintResultMsg, HealthResponse,
                                   ModifyRestRequest, PlanRestRequest, SearchRequestMsg, SearchResponseMsg,
                                   StyleRequestMsg, StyleResponseMsg)
from agents.fetch.specialists import budget_agent, search_agent, style_agent

orchestrator = Agent(name="orchestrator", seed=f"{config.AGENT_SEED_PREFIX}-orchestrator")

# request_id -> Future resolved when the specialist's reply arrives
_PENDING: dict = {}


def _resolve(msg) -> None:
    fut = _PENDING.get(getattr(msg, "request_id", ""))
    if fut is not None and not fut.done():
        fut.set_result(msg)


@orchestrator.on_message(model=SearchResponseMsg)
async def on_search_reply(ctx: Context, sender: str, msg: SearchResponseMsg):
    _resolve(msg)


@orchestrator.on_message(model=StyleResponseMsg)
async def on_style_reply(ctx: Context, sender: str, msg: StyleResponseMsg):
    _resolve(msg)


@orchestrator.on_message(model=ConstraintResultMsg)
async def on_check_reply(ctx: Context, sender: str, msg: ConstraintResultMsg):
    _resolve(msg)


class FetchBus:
    """AgentBus implementation over Fetch.ai uAgents messaging."""
    mode = "fetch"

    def __init__(self, ctx: Context):
        self.ctx = ctx

    async def _call(self, name: str, address: str, msg, response_type):
        rid = uuid.uuid4().hex
        msg.request_id = rid
        fut = asyncio.get_running_loop().create_future()
        _PENDING[rid] = fut
        try:
            await self.ctx.send(address, msg)
            resp = await asyncio.wait_for(fut, timeout=config.AGENT_CALL_TIMEOUT)
        except asyncio.TimeoutError:
            raise AgentUnavailable(f"{name} did not respond within {config.AGENT_CALL_TIMEOUT}s")
        finally:
            _PENDING.pop(rid, None)
        if not isinstance(resp, response_type):
            raise AgentUnavailable(f"{name} sent an unexpected reply: {type(resp).__name__}")
        return resp

    async def search(self, session_id, search_request, reason="", outfit_id=None):
        r = await self._call("search_agent", search_agent.address,
                             SearchRequestMsg(session_id=session_id, search_request=search_request,
                                              reason=reason, outfit_id=outfit_id), SearchResponseMsg)
        return r.products, r.events

    async def style(self, session_id, request, profile, contexts, products, outfit_id=None):
        r = await self._call("style_agent", style_agent.address,
                             StyleRequestMsg(session_id=session_id, request=request, profile=profile,
                                             contexts=contexts, products=products, outfit_id=outfit_id),
                             StyleResponseMsg)
        return r.scores, r.events

    async def check(self, session_id, request, outfits, check_outfit_ids=None):
        r = await self._call("budget_agent", budget_agent.address,
                             ConstraintCheckMsg(session_id=session_id, request=request, outfits=outfits,
                                                check_outfit_ids=check_outfit_ids), ConstraintResultMsg)
        return r.violations, r.events


@orchestrator.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"orchestrator {orchestrator.address}")
    ctx.logger.info(f"search_agent {search_agent.address}")
    ctx.logger.info(f"style_agent  {style_agent.address}")
    ctx.logger.info(f"budget_agent {budget_agent.address}")


@orchestrator.on_rest_get("/health", HealthResponse)
async def health(ctx: Context) -> HealthResponse:
    return HealthResponse(status="ok", agents={
        "orchestrator": orchestrator.address, "search_agent": search_agent.address,
        "style_agent": style_agent.address, "budget_agent": budget_agent.address})


@orchestrator.on_rest_post("/plan", PlanRestRequest, AgentRestResponse)
async def plan(ctx: Context, req: PlanRestRequest) -> AgentRestResponse:
    ctx.logger.info(f"plan request for session {req.session_id}")
    result = await plan_shopping(req.raw_request, req.user_id, req.session_id, req.profile, req.wardrobe,
                                 bus=FetchBus(ctx))
    return AgentRestResponse(**result)


@orchestrator.on_rest_post("/modify", ModifyRestRequest, AgentRestResponse)
async def modify(ctx: Context, req: ModifyRestRequest) -> AgentRestResponse:
    ctx.logger.info(f"modify request for session {req.session_id}: {req.message}")
    result = await modify_shopping(
        {"session_id": req.session_id, "user_id": req.user_id, "message": req.message,
         "target_outfit_id": req.target_outfit_id},
        req.profile, req.wardrobe, bus=FetchBus(ctx))
    return AgentRestResponse(**result)
