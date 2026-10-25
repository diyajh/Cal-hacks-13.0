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

## Live wardrobe and product evidence

The judged extension flow uses the active retailer page as the product source.
Open the side panel on a product page, upload one or more wardrobe photos, and
Aura sends them to the configured server-side vision provider. Detected items
can be corrected or removed before the deterministic product comparison runs.
The comparison will not return `SKIP` until wardrobe analysis has completed.

For local live data, add these server-only values to `backend/.env`:

```env
APIFY_API_TOKEN=...
OPENAI_API_KEY=...       # or ANTHROPIC_API_KEY=...
VISION_MODEL=            # optional provider-specific override
```

Without `APIFY_API_TOKEN`, product search reports `LIVE SEARCH NOT CONFIGURED`
and does not fabricate fallback retailer results. Without a vision key, the
upload UI reports `VISION NOT CONFIGURED`; the active real browser product
continues to be shown with its extraction-quality status.
