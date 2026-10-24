# agents/ — Person 1: AI, Fetch.ai agents, planning & replanning

```
agents/
├── core/                  # pure Python, stdlib only (no pip installs needed)
│   ├── contract.py        # builders/normalizers matching shared contract JSON exactly
│   ├── parser.py          # NL -> ShoppingRequest (LLM if key set, rule-based fallback; always keeps raw_request)
│   ├── llm.py             # tiny OpenAI/Anthropic HTTPS client (optional)
│   ├── taxonomy.py        # garments, colors, styles, occasions vocab
│   ├── scoring.py         # explainable 0-100 match scores + score_breakdown
│   ├── agent_logic.py     # what the Search / Style / Budget agents actually do
│   ├── planner.py         # builds outfits, reuse, check -> replan loop (MAX_REPLAN_ATTEMPTS=3)
│   ├── modifier.py        # "keep the top but replace the skirt in outfit 3" -> edit actions
│   ├── explain.py         # fact-only "why_it_works"
│   ├── bus.py             # AgentBus interface + LocalBus (in-process fallback)
│   └── engine.py          # plan_shopping() / modify_shopping() entry points
├── products/client.py     # calls Person 2's POST /products/search, falls back to local JSON
├── fetch/                 # Fetch.ai uAgents
│   ├── messages.py        # uAgents Model messages
│   ├── specialists.py     # search_agent, style_agent, budget_agent
│   ├── orchestrator.py    # orchestrator agent + FetchBus + REST endpoints for FastAPI
│   └── run_bureau.py      # runs all 4 agents in one process
├── mock_products.json     # mock Product[] (source: "mock") used until Apify is ready
├── demo.py                # CLI demo / example generator
└── tests/test_engine.py   # canonical San Diego test, replanning, modification, conflict
```

## Run it

```bash
# from the repo root
python -m unittest agents.tests.test_engine -v      # no installs needed
python -m agents.demo                               # prints the full agent trace

# Fetch.ai agents (works on Python 3.9+; 3.12 recommended for the latest uagents)
pip install -r agents/requirements.txt
python -m agents.fetch.run_bureau                   # REST on http://localhost:8001

curl -X POST localhost:8001/plan -H 'Content-Type: application/json' -d '{
  "raw_request": "I am going to San Diego for five days. I need five outfits. Each outfit should be under $50 and my total budget is $500. I want a beachy neutral aesthetic. One outfit needs a crochet top and skirt. I already own white sneakers. Remember that I own them.",
  "user_id": "user_123", "session_id": "session_abc"}'
```

## How the agents interact (real messages, real events)

```
FastAPI ──POST /plan──▶ ORCHESTRATOR (parses intent, runs planner)
                          │  SearchRequestMsg ───▶ SEARCH AGENT ──▶ /products/search (Person 2) or fallback JSON
                          │  StyleRequestMsg  ───▶ STYLE AGENT  (scores products per occasion, excludes avoided colors)
                          │  planner builds 5 outfits (wardrobe + reuse aware)
                          │  ConstraintCheckMsg ─▶ BUDGET AGENT ("$63 exceeds $50" → violation)
                          │  planner replans: SearchRequestMsg(max_price=$11) ─▶ SEARCH AGENT …
                          │  STYLE AGENT re-scores → swap → BUDGET AGENT re-checks ("$39 ≤ $50. Valid.")
                          ▼
                     FinalRecommendation (+ every AgentEvent each agent emitted)
```
Each specialist returns its own `AgentEvent`s inside its reply, so `agent_events` is a true trace.

## Integration — Person 2 (FastAPI)

**Primary (Fetch.ai):** call the orchestrator over HTTP.

| FastAPI endpoint | calls | body |
|---|---|---|
| `POST /shopping/plan` | `POST http://localhost:8001/plan` | `{raw_request, user_id, session_id, profile?, wardrobe?}` |
| `POST /shopping/modify` | `POST http://localhost:8001/modify` | `{session_id, user_id, message, target_outfit_id?, profile?, wardrobe?}` |

Response (`PlanResult`):
```json
{
  "final_recommendation": { ...FinalRecommendation (contract §20)... },
  "wardrobe_items_to_save": [ ...WardrobeItem... ],
  "conflict": null,
  "profile_updates": null
}
```
- Return `final_recommendation` to React as-is.
- Persist `wardrobe_items_to_save` (memory_type/expires_at already set per §9/§10).
- Pass the user's **active** wardrobe + profile in `wardrobe` / `profile` (I also drop expired temporary items).
- Set `PRODUCT_SEARCH_URL=http://localhost:8000/products/search` in `.env` for the agents. It accepts either a bare `Product[]` or `{"products": Product[]}`.

**Fallback (if the Fetch bureau is down):** call the same code in-process. The events will be honestly labelled as local mode.
```python
import sys; sys.path.insert(0, "<repo root>")
from agents.core.engine import plan_shopping, modify_shopping   # async
result = await plan_shopping(raw_request, user_id, session_id, profile, wardrobe)
```

## Integration — Person 3 (React)

- Real example outputs: `shared/examples/agents_final_recommendation.json`, `agents_modified_recommendation.json`.
- `agent_events[].agent` ∈ `orchestrator | planner | search_agent | style_agent | budget_agent`.
- Event types used: `request_received, request_parsed, memory, planning, search_started, search_completed, style_evaluated, outfit_created, constraint_check, constraint_violation, replanning, replacement_found, outfit_accepted, conflict, plan_completed, modification_parsed, mode`.
- Outfits come in **day order**. Sort by `match_score` if you show them as ranked alternatives.
- The same physical item keeps the same `OutfitItem.id` across outfits. `reused = used_in_outfits.length > 1`.
- `owned_items_used` and `reused_items` are lists of **OutfitItem** objects.
- On `/modify`, `agent_events` contains only the events from that modification.

## Decisions to confirm with the team (contract unchanged)

1. **Product categories** expected from Person 2: `top | bottom | dress | shoes | outerwear | accessory`. Common plurals/synonyms are mapped. Products with other categories are dropped.
2. **Conflict options** (§18) are returned beside FinalRecommendation as `conflict`, because FinalRecommendation has no field for them. The `message` field also explains the conflict. If Person 3 wants the options inside FinalRecommendation, we should agree to add `"conflict": null | {...}` to the contract.
3. **Per-outfit cost** counts the full price of every purchased piece in that outfit, even if it is reused elsewhere. **Trip total** counts each product once.
4. Session state for `/modify` lives in the orchestrator process (memory + `agents/.sessions/*.json`, gitignored).

## Fetch.ai agents (for judges)

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

An autonomous personal shopping and styling system: four uAgents turn one natural-language request
into complete outfits from real products, enforce hard budgets, reuse the shopper's own wardrobe, and
autonomously replan when a constraint fails. Chat with the orchestrator from ASI:One.

| Agent | Role | Address |
|---|---|---|
| **orchestrator** | Entry point (Chat Protocol + REST). Parses intent, plans outfits, drives the replanning loop. | `agent1qv6ukxyhvpannewqqlqw22p0x5vn8azesvww2r0z78t0uvhvjg0xgjzatfe` |
| **search_agent** | Retrieves normalized products (category, colors, max price) from the product service. | `agent1q0k4uu2x38n24a6hvrhq8gvt8gsqu4unf6egkslrhh0hakc7vdlf5dw7nvp` |
| **style_agent** | Scores products 0–100 for style, color, occasion and preferences; excludes avoided colors. | `agent1q2j4zjedfq7l43ndxhk22khpy98s7306zkvuzjpdxtc5m4gg65xzu766dp0` |
| **budget_agent** | Enforces hard constraints (per-outfit and trip budgets, required items) and rejects violations. | `agent1q2tujpy9t5p8223p0g77mrzvdmepf4tvyt87082he2aaau4jw0d8crakfcj` |

Example chat: *"I'm going to San Diego for five days. I need five outfits under $50 each, $500 total, beachy neutral,
one outfit needs a crochet top and skirt, I already own white sneakers."*
