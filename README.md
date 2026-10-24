# Aura — autonomous personal shopping agent

Aura turns a natural-language trip brief into constraint-checked outfits,
using live product research, wardrobe memory, and multi-agent replanning.

## Repository layout

- `src/` — React/TypeScript product experience and backend adapter.
- `backend/` — FastAPI boundary for voice, agent events, and future session APIs.

## Security boundary

Cartesia credentials are server-only. Do not put them in `VITE_*` variables,
the React bundle, screenshots, or commits. Copy `backend/.env.example` to
`backend/.env` locally and populate it with a rotated key.

## Local development

```bash
npm install
npm run dev

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The voice endpoint contract is in `backend/app/schemas.py`. Cartesia Ink STT
and Sonic TTS are isolated behind `backend/app/voice.py`; provider transport is
the next implementation slice.
