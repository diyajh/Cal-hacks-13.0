"""Create uAgents in a way that works on both old (Python 3.9) and new uagents versions."""
from __future__ import annotations

import inspect

from uagents import Agent

from agents import config

_PARAMS = set(inspect.signature(Agent.__init__).parameters)


def supports(param: str) -> bool:
    return param in _PARAMS


def make_agent(name: str, seed_suffix: str, description: str) -> Agent:
    kwargs = {"name": name, "seed": f"{config.AGENT_SEED_PREFIX}-{seed_suffix}"}
    if config.AGENTVERSE_MAILBOX and supports("mailbox"):
        kwargs["mailbox"] = True
    if supports("description"):
        kwargs["description"] = description
    agent = Agent(**kwargs)
    _add_auto_connect(agent)
    return agent


def _add_auto_connect(agent: Agent) -> None:
    """Connect the agent's Agentverse mailbox at startup using AGENTVERSE_API_KEY.

    Does the same thing as the inspector page's "Connect -> Mailbox" button: it calls the agent's
    own built-in /connect handler with your Agentverse token. Needed because the inspector page
    can't pick one agent out of a Bureau (all four share one port).
    """
    if not (config.AGENTVERSE_MAILBOX and config.AGENTVERSE_API_KEY):
        return
    try:
        from uagents.mailbox import AgentverseConnectRequest
    except ImportError:  # older uagents
        return

    @agent.on_event("startup")
    async def _agentverse_connect(ctx):
        handler = getattr(agent, "_rest_handlers", {}).get(("POST", "/connect"))
        if handler is None:
            ctx.logger.warning("Agentverse auto-connect unavailable in this uagents version")
            return
        try:
            resp = await handler(ctx, AgentverseConnectRequest(user_token=config.AGENTVERSE_API_KEY,
                                                               agent_type="mailbox"))
            if resp.success:
                ctx.logger.info("Agentverse mailbox connected")
            else:
                ctx.logger.warning(f"Agentverse mailbox connect failed: {resp.detail}")
        except Exception as exc:  # never block startup
            ctx.logger.warning(f"Agentverse mailbox connect error: {exc}")
