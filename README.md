# Aura

Aura is a voice-first AI shopping agent for the Chrome side panel. It combines a user’s style profile, saved wardrobe, budget, and live retailer data to build explainable outfits and product decisions. Aura plans purchases; it does not collect card details, process payments, or provide checkout.

## Architecture

```text
Chrome side panel / React + Vite (:5173)
        │
        ▼
FastAPI gateway (:8019)
   ├── Cartesia voice
   ├── OpenAI Vision wardrobe analysis
   ├── SQLite wardrobe metadata
   ├── Apify product search
   └── Fetch/uAgents orchestrator (:8017)
             ├── request parsing
             ├── style/profile filtering
             ├── wardrobe reuse
             ├── budget validation
             └── replanning
```

The extension content script extracts the active retailer page using JSON-LD, OpenGraph, and visible-page fallbacks. Only structured wardrobe metadata is persisted; uploaded photos are analyzed and discarded.

## Sponsor track integrations

### Visa — Reimagining Shopping with AI

Aura demonstrates personalized shopping decisions using a style profile, wardrobe inventory, live product results, and deterministic budget validation. It makes reuse, savings, explanations, and BUY/SKIP decisions visible. Visa did not provide a proprietary API for this project, so Aura does not claim Visa payment processing, card storage, or direct retailer checkout.

### Fetch.ai/uAgents

The local uAgents orchestration layer coordinates four roles: the Orchestrator Agent receives the request, the Search Agent retrieves candidates, the Style Agent applies profile and compatibility filtering, and the Budget Agent validates totals and triggers replanning. Together they coordinate live search, style constraints, wardrobe reuse, budget checks, and targeted modifications. This repository uses local Fetch/uAgents orchestration; Agentverse and ACP registration are not claimed.

### Apify

Apify supplies live product retrieval through the product-search service. Results are normalized into the shared `Product` structure and checked for title, retailer, price, currency, image, source, and an exact retailer URL. Google Shopping redirects and incomplete products are rejected. When live data is unavailable, Aura does not present fabricated or mock products as live results.

### Cartesia

Cartesia provides Ink-Whisper speech-to-text and Sonic text-to-speech. Voice requests are transcribed and sent through the same planning path as typed requests; the returned response can be spoken back to the user.

### OpenAI Vision

OpenAI Vision analyzes uploaded wardrobe photos into structured metadata such as category, color, subtype, style, and confidence. Original photos are discarded after analysis; only the user-approved structured wardrobe metadata is stored.

## Setup

Prerequisites: Node.js 18+, Python 3.10+, and Chrome with Developer mode enabled.

```bash
git clone <repository-url>
cd Cal-hacks-13.0
npm install
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
cp backend/.env.example backend/.env
cp agents/.env.example agents/.env
```

Use local environment files only. They are ignored by Git and must never contain values committed to the repository.

## Environment variables

```dotenv
APIFY_API_TOKEN=
OPENAI_API_KEY=
CARTESIA_API_KEY=
AGENTS_BASE_URL=http://127.0.0.1:8017
PRODUCT_SEARCH_URL=http://127.0.0.1:8019/products/search
AGENTS_PORT=8017
AURA_DATABASE_URL=sqlite:///backend/data/aura.sqlite3
VITE_API_BASE_URL=http://127.0.0.1:8019
```

The live demo requires an Apify token, OpenAI Vision key, and Cartesia key. The database stores wardrobe metadata only; temporary memory expires after 30 days and remembered items remain until removed.

## Start the local services

Fetch terminal, from the repository root:

```bash
AGENTS_PORT=8017 \
PRODUCT_SEARCH_URL=http://127.0.0.1:8019/products/search \
backend/.venv/bin/python -m agents.fetch.run_bureau
```

FastAPI terminal:

```bash
cd backend
AGENTS_BASE_URL=http://127.0.0.1:8017 \
../backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8019
```

Frontend terminal:

```bash
cd ..
npm run dev -- --host 127.0.0.1 --port 5173
```

Build and load the Chrome extension:

```bash
npm run build
```

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select the repository’s `dist/` directory. Open a real retailer page, open Aura in the side panel, and refresh product detection if needed.

## Demo flow

Use this request:

> One date-night outfit under $100 with a top, bottom, and shoes.

Aura validates all three required categories, reuses compatible wardrobe items at $0, searches live products for remaining slots, filters products against the profile, and rejects invalid or over-budget plans. The result shows the requested look count, planned spend, reuse, reasoning, and available retailer links.

## Tests and checks

```bash
npm run build
node tests/ui_polish.test.cjs
node tests/planner_budget_ui.test.cjs
node tests/product-quality.test.cjs
node --check public/content.js
node --check public/background.js
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -v
PYTHONPATH=. backend/.venv/bin/python -m unittest discover -s agents/tests -v
python3 -m compileall -q backend agents
git diff --check
```

## Privacy and limitations

Aura stores structured wardrobe attributes such as category, color, subtype, style, confidence, and memory status in local SQLite metadata. It does not store uploaded wardrobe photos. Missing or incomplete retailer data is surfaced rather than invented. Product availability, prices, images, and links depend on the active retailer page and live Apify response. Fetch/uAgents runs locally in this repository; Agentverse/ACP registration is not verified. Aura does not provide payment processing or checkout.
