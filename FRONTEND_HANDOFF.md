# Aura frontend handoff

## What is implemented

- One judge-friendly happy path from natural-language prompt to ranked trip looks.
- Typed mock-first contracts in `src/types.ts`.
- A realistic San Diego response in `src/mockData.ts`.
- Request understanding chips, agent activity timeline, wardrobe reuse, match scores, “why this works,” day filtering, text input, voice affordance, and checkout summary.
- The UI intentionally shows agent work as a calm product timeline rather than terminal output.

## Minimum structure

`App.tsx` is currently the fast-demo composition root. The first extraction pass should be:

```text
src/
  App.tsx
  types.ts
  mockData.ts
  styles.css
  components/
    PromptComposer.tsx
    RequestSummary.tsx
    AgentActivity.tsx
    OutfitCard.tsx
    ProductCard.tsx
    CheckoutBar.tsx
  api/
    client.ts
```

Keep the same `StyleSession` shape while swapping the mock import for `getStyleSession()`.

The first adapter is already scaffolded in `src/api/client.ts`:

- `createStyleSession(prompt)` → `POST /api/style-sessions`
- `getStyleSession(sessionId)` → `GET /api/style-sessions/:id`
- `modifyStyleSession(sessionId, instruction)` → `POST /api/style-sessions/:id/modifications`

Set `VITE_API_BASE_URL` when the FastAPI service is ready. Leave it unset to keep the mock demo fully offline.

## Voice sponsor seam

`src/voiceAgent.ts` defines the visible voice-agent state machine. Browser Speech Recognition is the local demo fallback. When Cartesia is connected, the frontend should send transcript text to `sendVoiceTurn()` and receive the response text/audio metadata from FastAPI. Keep Cartesia credentials server-side; do not put them in Vite environment variables exposed to the browser.

## Backend seam

The API should return `StyleSession` (or a versioned envelope around it). Agent events can arrive as a stream later; for the first integration, returning the complete `agent_events` array is enough. The UI currently accepts `status: 'done' | 'active'`, so a websocket/SSE adapter can append events without changing the visual layer.

## Demo path

1. Use the placeholder prompt or click a suggested prompt.
2. Show the interpreted request and constraint chips.
3. Point to the rejected `$67` outfit and cheaper replacement in the activity feed.
4. Call out the white sneakers as reused at `$0`.
5. Switch Day 1 / Day 2 / Day 3 to show ranked alternatives.
6. Continue to checkout.

Text entry is the reliable fallback. The voice button is intentionally isolated so Browser Speech Recognition can be connected without coupling it to the results UI.
