# Aura backend

This service is the server-side boundary for Cartesia and the agent system.
The browser must send transcript/audio to this service; it must never receive
`CARTESIA_API_KEY`.

## Local setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

For the live shopping and wardrobe evidence flow, populate `backend/.env` with
`APIFY_API_TOKEN` and exactly one of `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY`. Wardrobe uploads use `POST /wardrobe/analyze`; product
comparisons use `POST /wardrobe/decision`. If a provider is not configured,
the API returns an explicit setup error rather than demo wardrobe or product
data. `POST /products/search` likewise reports `LIVE SEARCH NOT CONFIGURED`
when Apify is unavailable.

The first implementation slice exposes `/health` and the typed voice-turn
contract. The Cartesia transport is intentionally isolated in
`app/voice.py`; it will be implemented against Ink STT and Sonic TTS without
changing the frontend route contract.

