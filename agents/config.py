"""Environment configuration for the agent system.

All values are optional; sensible defaults let the demo run with zero setup.
"""
import os
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENTS_DIR.parent


def _load_dotenv() -> None:
    """Tiny .env loader so we don't need python-dotenv. Never overrides real env vars."""
    for candidate in (REPO_ROOT / ".env", AGENTS_DIR / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Person 2's normalized product search endpoint (POST, ProductSearchRequest -> Product[]).
# Leave empty to use local fallback/mock products.
PRODUCT_SEARCH_URL = os.environ.get("PRODUCT_SEARCH_URL", "").strip()
PRODUCT_SEARCH_TIMEOUT = _int("PRODUCT_SEARCH_TIMEOUT", 25)

# Fallback catalogs, tried in order. fallback-data/products.json is owned by Person 2.
FALLBACK_PRODUCT_FILES = [
    REPO_ROOT / "fallback-data" / "products.json",
    AGENTS_DIR / "mock_products.json",
]

MAX_REPLAN_ATTEMPTS = _int("MAX_REPLAN_ATTEMPTS", 3)

# LLM (optional). If no key is set, the deterministic rule-based parser is used.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "").strip()  # override default model name
LLM_TIMEOUT = _int("LLM_TIMEOUT", 20)

# Fetch.ai
ORCHESTRATOR_PORT = _int("AGENTS_PORT", 8001)
AGENT_SEED_PREFIX = os.environ.get("AGENT_SEED_PREFIX") or "calhacks13-shopping-dev-seed"
AGENT_CALL_TIMEOUT = _int("AGENT_CALL_TIMEOUT", 60)

# Agentverse: set AGENTVERSE_MAILBOX=true to connect the agents to Agentverse via mailboxes
# (then open the "Agent inspector" link each agent prints and click Connect -> Mailbox).
AGENTVERSE_MAILBOX = os.environ.get("AGENTVERSE_MAILBOX", "").strip().lower() in ("1", "true", "yes", "all")
# Used at startup to auto-connect each agent's Agentverse mailbox (see agents/fetch/factory.py).
AGENTVERSE_API_KEY = os.environ.get("AGENTVERSE_API_KEY", "").strip()

SESSION_DIR = AGENTS_DIR / ".sessions"
