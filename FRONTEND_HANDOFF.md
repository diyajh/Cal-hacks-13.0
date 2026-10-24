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

The frontend adapter now targets Person 2's gateway:

- `createStyleSession(prompt)` → `POST /shopping/plan` with `{ raw_request, user_id, session_id }`
- `modifyStyleSession(sessionId, instruction)` → `POST /shopping/modify` with `{ session_id, user_id, message, target_outfit_id: null }`
- The gateway forwards planning to Person 1 and returns `final_recommendation`, `conflict`, and `wardrobe_items_to_save`.
- Real product fields are normalized from `image_url` and `product_url` into the UI's `image` and `link` fields.
- `conflict.status === "needs_user_input"` is shown as an explicit choice instead of rendering an invalid plan.

Set `VITE_API_BASE_URL` when the FastAPI service is ready. Leave it unset to keep the mock demo fully offline.

## Voice sponsor seam

`src/voiceAgent.ts` defines the visible voice-agent state machine. Browser Speech Recognition is the local demo fallback. When Cartesia is connected, the frontend should send transcript text to `sendVoiceTurn()` and receive the response text/audio metadata from FastAPI. Keep Cartesia credentials server-side; do not put them in Vite environment variables exposed to the browser.

## Backend seam

The API returns the agent contract unchanged. `final_recommendation.outfits[].items[]` may contain either a live `product` or a `wardrobe_item`; `purchase_required === false` marks reuse. The UI derives the smart purchase plan from those items and only links to a non-empty real `product_url`. Agent events arrive as a complete `agent_events` array; no streaming dependency is required for the demo.

## Demo path

1. Use the placeholder prompt or click a suggested prompt.
2. Show the interpreted request and constraint chips.
3. Point to the rejected `$67` outfit and cheaper replacement in the activity feed.
4. Call out the white sneakers as reused at `$0`.
5. Switch Day 1 / Day 2 / Day 3 to show ranked alternatives.
6. Continue to checkout.

Text entry is the reliable fallback. The voice button is intentionally isolated so Browser Speech Recognition can be connected without coupling it to the results UI.
