# Aura — autonomous personal shopping agent

Aura turns a natural-language trip brief into constraint-checked outfits,
using live product research, wardrobe memory, and multi-agent replanning.

## Repository layout

- `src/` — React/TypeScript product experience and backend adapter.
- `backend/` — FastAPI boundary for voice, agent events, and session APIs.
- `public/manifest.json` — Manifest V3 extension shell for the Aura side panel.

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

For the extension build, run `npm run build`, then open `chrome://extensions`,
enable Developer mode, choose **Load unpacked**, and select the repository's
`dist/` folder. Start the backend separately and set `VITE_API_BASE_URL` before
starting Vite when testing live planning locally.

The extension uses a side panel plus a content script that extracts structured
page metadata (title, URL, description, and product JSON-LD when available).
The browser sends that context to the server; Cartesia Ink STT and Sonic TTS
remain behind the FastAPI boundary and no API key enters the extension bundle.
