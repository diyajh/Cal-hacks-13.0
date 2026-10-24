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

The first implementation slice exposes `/health` and the typed voice-turn
contract. The Cartesia transport is intentionally isolated in
`app/voice.py`; it will be implemented against Ink STT and Sonic TTS without
changing the frontend route contract.

