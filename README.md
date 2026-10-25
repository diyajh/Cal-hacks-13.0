# Aura

Aura is a Chrome side-panel shopping concierge. A user describes a trip or occasion by voice or text, and Aura combines their saved wardrobe, profile constraints, budget, live retailer research, and agent reasoning into explainable outfit recommendations. It can also compare the product on the current browser page against the wardrobe and explain a BUY, SKIP, or “needs more detail” decision.

Aura is a planning and discovery experience. It does not collect payment-card details, provide checkout, or claim direct retailer checkout. A live FastAPI, Fetch/uAgents, Apify, vision, and Cartesia setup is required for the complete flow; typed requests are not a fully offline mode.

## Architecture

```text
Chrome side panel / React + Vite (:5173)
        │
        ▼
FastAPI gateway (:8019)
   ├── Cartesia Ink STT / Sonic TTS
   ├── vision provider for wardrobe photos
   ├── SQLite wardrobe metadata
   ├── live Apify product search
   └── Fetch/uAgents orchestrator (:8017)
             ├── request parsing
             ├── style and profile filtering
             ├── budget and constraint checks
             └── replanning
```

The extension content script extracts the active retailer page using JSON-LD, OpenGraph, and visible-page fallbacks. Only structured wardrobe metadata is persisted; uploaded photos are analyzed and discarded rather than stored.

Fetch/uAgents is used as the local orchestration layer in this repository. Agentverse/ACP registration and direct retailer checkout are not prerequisites or claims of this demo.

## Prerequisites

- Node.js 18+
- Python 3.10+
- Google Chrome with Developer mode enabled
- Optional live credentials: Apify, one vision provider, and Cartesia

## Setup

```bash
git clone <repository-url>
cd Cal-hacks-13.0
npm install
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

Copy the templates and fill them locally. Never commit populated environment files:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp agents/.env.example agents/.env
```

The root `.env` is used by Vite. Server credentials belong in `backend/.env`; agent configuration belongs in `agents/.env`. Both are ignored by Git.

## Environment variables

Required for the complete live demo:

- `APIFY_API_TOKEN` — live product search.
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — wardrobe-photo analysis.
- `CARTESIA_API_KEY` — browser voice transcription and response audio.
- `AGENTS_BASE_URL=http://localhost:8017` — FastAPI-to-agent gateway.
- `PRODUCT_SEARCH_URL=http://localhost:8019/products/search` — agent-to-FastAPI live search route.
- `AGENTS_PORT=8017` — local uAgents REST port.
- `AURA_DATABASE_URL=sqlite:///backend/data/aura.sqlite3` — durable wardrobe metadata.
- `VITE_API_BASE_URL=http://localhost:8019` — frontend gateway.

Optional settings include `VISION_MODEL`, Cartesia model/voice variables, `ALLOWED_ORIGINS`, `PRODUCT_SEARCH_TIMEOUT`, and `REPLAN_SEARCH`. Use empty values in the templates until you have real credentials. Do not put server keys in `VITE_*` variables.

## Start the local services

Use separate terminals from the repository root:

```bash
AGENTS_PORT=8017 PYTHONPATH=. backend/.venv/bin/python -m agents.fetch.run_bureau
```

Start FastAPI on the gateway port:

```bash
AGENTS_BASE_URL=http://localhost:8017 backend/.venv/bin/uvicorn backend.app.main:app --reload --port 8019
```

Start Vite:

```bash
VITE_API_BASE_URL=http://localhost:8019 npm run dev -- --host 127.0.0.1 --port 5173
```

## Build and load the extension

```bash
npm run build
```

Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select the repository `dist/` directory. Open a real retailer product page, open Aura from the side panel, and use **Refresh product detection** if needed.

## Demo flow

Use this request:

> One date-night outfit under $100 with a top, bottom, and shoes.

Aura parses all three required slots, reuses compatible saved wardrobe pieces at $0, searches live products for remaining slots, filters products against the profile, and rejects any complete outfit whose combined new-product total exceeds $100. The final plan shows the exact look count, planned spend, reuse, reasoning, and retailer links available from the live response.

For voice, say the same sentence after microphone permission is granted. Voice and typed requests use the same planning submit path.

## Tests and checks

```bash
npm run build
node tests/ui_polish.test.cjs
node tests/planner_budget_ui.test.cjs
node --check public/content.js
node --check public/background.js
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -v
PYTHONPATH=. backend/.venv/bin/python -m unittest discover -s agents/tests -v
python3 -m compileall -q backend agents
git diff --check
```

## Privacy and limitations

Aura stores structured wardrobe attributes such as category, color, style, confidence, and memory status in local SQLite metadata. It does not store uploaded wardrobe photos. Temporary memory expires after 30 days; remembered items remain until removed. Resetting a demo session does not delete persistent wardrobe memory. Users can edit, delete individual items, or clear all wardrobe memory.

Live product availability, retailer fields, images, prices, and links depend on the active retailer page and Apify response. Missing or incomplete product data is surfaced rather than fabricated. Without a vision key, Apify token, or Cartesia key, the relevant capability reports a clear unavailable state. The demo does not provide payment processing or checkout.
