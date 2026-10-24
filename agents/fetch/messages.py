"""uAgents message models (Python 3.9-compatible typing: use Optional, not `X | None`).
request_id correlates a reply with its request, so we don't depend on ctx.send_and_receive
(which older uagents versions lack).

uAgents message models exchanged between the orchestrator and specialist agents.
Payloads are contract-shaped dicts (Product, Outfit, AgentEvent, ConstraintViolation)."""
from typing import Any, Optional

from uagents import Model


# orchestrator -> search_agent
class SearchRequestMsg(Model):
    session_id: str
    request_id: str = ""
    search_request: dict[str, Any]
    reason: str = ""
    outfit_id: Optional[str] = None


class SearchResponseMsg(Model):
    session_id: str
    request_id: str = ""
    products: list[dict[str, Any]]
    events: list[dict[str, Any]]


# orchestrator -> style_agent
class StyleRequestMsg(Model):
    session_id: str
    request_id: str = ""
    request: dict[str, Any]
    profile: Optional[dict[str, Any]] = None
    contexts: list[dict[str, Any]]
    products: list[dict[str, Any]]
    outfit_id: Optional[str] = None


class StyleResponseMsg(Model):
    session_id: str
    request_id: str = ""
    scores: dict[str, Any]
    events: list[dict[str, Any]]


# orchestrator -> budget_agent
class ConstraintCheckMsg(Model):
    session_id: str
    request_id: str = ""
    request: dict[str, Any]
    outfits: list[dict[str, Any]]
    check_outfit_ids: Optional[list[str]] = None


class ConstraintResultMsg(Model):
    session_id: str
    request_id: str = ""
    violations: list[dict[str, Any]]
    events: list[dict[str, Any]]


# FastAPI -> orchestrator (REST)
class PlanRestRequest(Model):
    raw_request: str
    user_id: str
    session_id: str
    profile: Optional[dict[str, Any]] = None
    wardrobe: list[dict[str, Any]] = []


class ModifyRestRequest(Model):
    session_id: str
    user_id: str
    message: str
    target_outfit_id: Optional[str] = None
    profile: Optional[dict[str, Any]] = None
    wardrobe: Optional[list[dict[str, Any]]] = None


class AgentRestResponse(Model):
    final_recommendation: dict[str, Any]
    wardrobe_items_to_save: list[dict[str, Any]] = []
    conflict: Optional[dict[str, Any]] = None
    profile_updates: Optional[dict[str, Any]] = None


class HealthResponse(Model):
    status: str
    agents: dict[str, str]
