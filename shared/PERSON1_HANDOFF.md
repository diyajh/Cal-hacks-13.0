# Person 1 handoff — AI / Fetch.ai agents / planning & replanning

Branch: `agents`. Everything lives in `agents/` (+ examples in `shared/examples/`).
Shared contract (`shared/CONTRACT.md` / team spec) is **unchanged** — all outputs follow it exactly.
Claude sessions: read this file, then `agents/README.md`, before touching agent code or integrating with it.

---

## 1. Status

| Feature | Status |
|---|---|
| Natural language → `ShoppingRequest` | ✅ Rule-based parser (handles "$50 each", "50$", "500 total", lowercase cities, "looks"…). LLM parser built in, **activates when `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set** (not set yet). |
| 4 Fetch.ai uAgents (orchestrator, search, style, budget) exchanging real messages | ✅ Verified running on Python 3.12 + uagents 0.26.1 |
| Registered on Almanac + **connected to Agentverse via mailbox** | ✅ All 4 show "Agentverse mailbox connected" |
| Chat Protocol (ASI:One discoverability) on orchestrator | ✅ Manifest published. ⏳ End-to-end chat from ASI:One not yet confirmed |
| Outfit planning, wardrobe reuse, item reuse across outfits | ✅ |
| Hard-constraint checks (per-outfit $, trip total $ with reused items counted once, required items, outfit count, completeness) | ✅ |
| Autonomous replanning (MAX 3 attempts) → `needs_user_input` conflict with options if impossible | ✅ |
| Match score 1–100 + `score_breakdown` + fact-only `why_it_works` | ✅ |
| Conversational modifications (`/modify`) touching only affected outfits | ✅ |
| Real `AgentEvent`s from each agent (for the activity UI) | ✅ (returned with the response, not streamed live) |
| REST API for FastAPI: `POST /plan`, `POST /modify`, `GET /health` on :8001 | ✅ |
| Live products from Person 2 `/products/search` | ⏳ Client ready; uses `agents/mock_products.json` until `PRODUCT_SEARCH_URL` is set |
| Tests | ✅ `python3 -m unittest agents.tests.test_engine` (11) and `python3 -m agents.check all` (16/16) |

---

## 2. Run it

```bash
cd Cal-hacks-13.0
python3.12 -m venv .venv && source .venv/bin/activate      # Python >= 3.10 needed for Agentverse/chat
pip install -r agents/requirements.txt
cp agents/.env.example .env                                 # then fill values (never commit .env)
python -m agents.fetch.run_bureau                           # starts all 4 agents, REST on :8001
python3 -m agents.try_it                                    # (2nd terminal) type requests, see agent trace
```
No-install checks: `python3 -m agents.check all`, `python3 -m agents.check plan`, `python3 -m agents.check chat "..."`.

`.env` keys used by agents: `AGENTVERSE_MAILBOX`, `AGENTVERSE_API_KEY` (auto-connects mailboxes at startup),
`AGENT_SEED_PREFIX` (secret; determines agent addresses — don't change it or addresses change),
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `LLM_MODEL`, `PRODUCT_SEARCH_URL`, `AGENTS_PORT`.

---

## 3. For Person 2 (FastAPI / Apify / DB)

**Your `/shopping/plan` → call** `POST http://localhost:8001/plan`
```json
{"raw_request": "...", "user_id": "user_123", "session_id": "session_abc", "profile": {...UserProfile} , "wardrobe": [...active WardrobeItem]}
```
**Your `/shopping/modify` → call** `POST http://localhost:8001/modify`
```json
{"session_id": "session_abc", "user_id": "user_123", "message": "replace the skirt in outfit 3", "target_outfit_id": null}
```
**Both return:**
```json
{
  "final_recommendation": { ...FinalRecommendation, send to React unchanged... },
  "wardrobe_items_to_save": [ ...WardrobeItem with memory_type/expires_at already set... ],
  "conflict": null | {"status":"needs_user_input","message":"...","conflicting_constraints":[...],"options":[...]},
  "profile_updates": null | {...}
}
```
- Persist `wardrobe_items_to_save` (e.g. "I own white sneakers. Remember that" → `remembered`, else `temporary` +30 days).
- `profile`/`wardrobe` are optional; pass the user's **active** wardrobe if you have it.
- Allow up to ~60–120 s timeout on these calls (Apify searches happen inside).
- If the agents are down, fallback in-process (events are honestly labelled "local mode"):
  `from agents.core.engine import plan_shopping, modify_shopping` (async, stdlib-only, no installs).

**What the Search Agent sends to your `/products/search`** (set `PRODUCT_SEARCH_URL=http://localhost:8000/products/search` in `.env`):
```json
{"query": "beachy crochet top", "category": "top", "colors": ["beige","white"], "tags": ["beachy","coastal","beach","brunch"], "max_price": 50.0, "limit": 20}
```
Return `Product[]` or `{"products": Product[]}` per the contract. **Please use categories**
`top | bottom | dress | shoes | outerwear | accessory` (plurals/synonyms like "tops", "skirts", "sneakers" are mapped;
anything else is dropped). Products missing `id`, `name`, `price` or a known category are ignored.
If your API fails/times out, agents fall back to `fallback-data/products.json` (yours), then `agents/mock_products.json`.

---

## 4. For Person 3 (React)

- Build against real outputs: `shared/examples/agents_final_recommendation.json` and `agents_modified_recommendation.json`.
- `agent_events[].agent` ∈ `orchestrator | planner | search_agent | style_agent | budget_agent`.
- Event `type`s: `request_received, request_parsed, memory, planning, search_started, search_completed, style_evaluated,
  outfit_created, constraint_check, constraint_violation, replanning, replacement_found, outfit_accepted, conflict,
  plan_completed, modification_parsed, mode`. `status` ∈ `working | completed | failed`.
- Outfits are in **day order**; sort by `match_score` if you show them as ranked alternatives.
- Same physical item keeps the same `OutfitItem.id` across outfits; `reused = used_in_outfits.length > 1`.
- `owned_items_used` and `reused_items` are lists of **OutfitItem**.
- On `/modify`, `agent_events` contains only that modification's events.
- When `status == "needs_user_input"`, show `message`; options are in the sibling `conflict.options` (see §6).
- A typical plan returns ~70–80 events at the end of the request (no streaming yet) — animate them sequentially.

---

## 5. Fetch.ai / Agentverse

| Agent | Address |
|---|---|
| orchestrator (chat protocol, entry point) | `agent1qv6ukxyhvpannewqqlqw22p0x5vn8azesvww2r0z78t0uvhvjg0xgjzatfe` |
| search_agent | `agent1q0k4uu2x38n24a6hvrhq8gvt8gsqu4unf6egkslrhh0hakc7vdlf5dw7nvp` |
| style_agent | `agent1q2j4zjedfq7l43ndxhk22khpy98s7306zkvuzjpdxtc5m4gg65xzu766dp0` |
| budget_agent | `agent1q2tujpy9t5p8223p0g77mrzvdmepf4tvyt87082he2aaau4jw0d8crakfcj` |

These addresses come from Person 1's private `AGENT_SEED_PREFIX`. Only one machine should run the registered agents
(Person 1's laptop / demo machine). Teammates running the bureau without that seed get different, unregistered addresses —
fine for local dev.

---

## 6. Open decisions for the team (contract NOT changed)
1. **Conflict options** are returned beside `final_recommendation` as `conflict` (FinalRecommendation has no field for them).
   If React wants them inside FinalRecommendation, agree to add `"conflict": null | {...}` to the contract.
2. **Per-outfit cost** = full price of every purchased piece in that outfit (even if reused elsewhere); **trip total** counts each product once.
3. **Product categories** as listed in §3.

---

## 7. Remaining Person 1 work
- [ ] Confirm chat end-to-end from ASI:One / Agentverse chat; set agents' category to Innovation Lab on Agentverse.
- [ ] Add an LLM key (Fetch prize asks for an LLM reasoning engine; also improves free-form parsing).
- [ ] Switch to Person 2's live `/products/search`; fix any category/format mismatches.
- [ ] (Optional) Stream events live to the UI; preference learning from `/feedback`.
