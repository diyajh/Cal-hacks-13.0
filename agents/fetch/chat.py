"""ASI:One / Agentverse Chat Protocol for the orchestrator.

Lets anyone chat with the shopping agent from ASI:One or Agentverse: a ChatMessage with the
user's request runs the full multi-agent plan (or a modification of their last plan) and the
orchestrator replies with a ChatMessage containing the outfits.

Requires a recent uagents (Python >= 3.10). On older installs this module is skipped and the
REST API keeps working.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("agents.chat")

try:
    from uagents import Context, Protocol
    from uagents_core.contrib.protocols.chat import (ChatAcknowledgement, ChatMessage, TextContent,
                                                     chat_protocol_spec)
    CHAT_AVAILABLE = True
except ImportError:  # old uagents without uagents_core chat protocol
    CHAT_AVAILABLE = False

from agents.core.engine import load_session, modify_shopping, plan_shopping
from agents.core.modifier import interpret_modification

_TASKS: set = set()
NEW_PLAN_WORDS = ("new trip", "start over", "new plan", "another trip", "instead plan")


def _usd(x) -> str:
    return f"${x:,.2f}"


def format_reply(result: dict, is_modification: bool = False) -> str:
    """Markdown summary of a PlanResult for chat."""
    rec = result["final_recommendation"]
    lines = [f"**{rec['message']}**", ""]
    if rec["status"] == "needs_user_input" and result.get("conflict"):
        lines.append("Options:")
        for i, opt in enumerate(result["conflict"]["options"], 1):
            lines.append(f"{i}. {opt}")
        lines.append("")
    for o in rec["outfits"]:
        pieces = []
        for it in o["items"]:
            d = it["product"] or it["wardrobe_item"]
            if it["source_type"] == "wardrobe":
                pieces.append(f"{d['name']} *(you own this)*")
            else:
                link = f"[{d['name']}]({d['product_url']})" if d.get("product_url") else d["name"]
                pieces.append(f"{link} {_usd(d['price'])}")
        flag = "" if o["constraints_satisfied"] else " ⚠️"
        lines.append(f"**Day {o['day']} — {o['title']}** · match {o['match_score']}/100 · "
                     f"{_usd(o['new_purchase_cost'])}{flag}")
        lines.append("  " + " + ".join(pieces))
    if rec["outfits"]:
        tb = f" of {_usd(rec['total_budget'])}" if rec.get("total_budget") is not None else ""
        lines += ["", f"**New purchases: {_usd(rec['total_new_purchase_cost'])}{tb}** (reused items counted once)"]

    ev = rec["agent_events"]
    rejected = sum(1 for e in ev if e["type"] == "constraint_violation")
    swaps = sum(1 for e in ev if e["type"] == "replacement_found")
    searches = sum(1 for e in ev if e["type"] == "search_completed")
    lines += ["", f"_Agent activity: {searches} product searches · budget agent rejected {rejected} candidate(s) · "
                  f"{swaps} autonomous replacement(s)._"]
    if rec["outfits"] and not is_modification:
        lines.append("_Try: \"Keep the top in outfit 3 but replace the skirt and make it more elegant\" or "
                     "\"my total budget is now $300\"._")
    return "\n".join(lines)


def _is_modification(text: str, session: dict | None) -> bool:
    if not session:
        return False
    low = text.lower()
    if any(w in low for w in NEW_PLAN_WORDS):
        return False
    outfits = session["planner"]["outfits"]
    return interpret_modification(text, None, outfits)["understood"]


async def handle_chat_text(text: str, sender: str, bus) -> str:
    """Shared by the uAgents chat handler (and testable without uagents)."""
    sid = "chat_" + sender[-16:]
    session = load_session(sid)
    if _is_modification(text, session):
        result = await modify_shopping({"session_id": sid, "user_id": sender, "message": text,
                                        "target_outfit_id": None}, bus=bus)
        return format_reply(result, is_modification=True)
    result = await plan_shopping(text, sender, sid, bus=bus)
    return format_reply(result)


def build_chat_protocol(make_bus):
    """make_bus(ctx) -> AgentBus. Returns a Protocol, or None if chat isn't available."""
    if not CHAT_AVAILABLE:
        return None
    proto = Protocol(spec=chat_protocol_spec)

    @proto.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
        text = msg.text().strip()
        if not text:
            return
        ctx.logger.info(f"chat from {sender[:16]}...: {text[:80]}")

        async def run():
            try:
                reply = await handle_chat_text(text, sender, make_bus(ctx))
            except Exception as exc:  # never leave the user hanging
                log.exception("chat handling failed")
                reply = f"Sorry - the shopping agents hit an error: {exc}"
            await ctx.send(sender, ChatMessage([TextContent(reply)]))

        # Run in the background: the orchestrator processes messages one at a time, and the plan
        # needs the specialists' reply messages to reach it while we wait (else: deadlock).
        task = asyncio.create_task(run())
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)

    @proto.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    return proto
