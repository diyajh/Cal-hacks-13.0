import { demoSession } from '../mockData'
import { AgentEvent, LiveStatus, Outfit, Product, ProductDecision, SessionConflict, StyleProfile, StyleSession, WardrobeItem } from '../types'
import { VoiceAgentResponse } from '../voiceAgent'

/**
 * Backend adapter for the React layer.
 *
 * Keep API details here so components only deal with StyleSession objects.
 * The extension uses the local live gateway; service readiness comes from /health.
 */
const extensionRuntime = Boolean((globalThis as any).chrome?.runtime?.id)
const configuredBase = (import.meta as any).env?.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
// Browser development can use the legacy gateway on 8000; the unpacked
// extension uses the merged live gateway on 8019. Both remain overrideable.
const API_BASE_URL = configuredBase || (extensionRuntime ? 'http://127.0.0.1:8019' : 'http://127.0.0.1:8000')
const VOICE_API_BASE_URL = (import.meta as any).env?.VITE_VOICE_API_BASE_URL?.replace(/\/$/, '') || (extensionRuntime ? 'http://127.0.0.1:8019' : 'http://127.0.0.1:8018')
const USER_ID = (import.meta as any).env?.VITE_AURA_USER_ID || 'demo_user'

export let apiConfigured = false

export async function getSavedWardrobe(): Promise<WardrobeItem[]> {
  const items = await request<any[]>(`/users/${encodeURIComponent(USER_ID)}/wardrobe`)
  return items.map(item => ({ ...item, source: 'wardrobe' as const, memory_type: item.memory_type ?? 'temporary' }))
}

export async function saveWardrobeItem(item: WardrobeItem, memoryType: 'temporary' | 'remembered' = 'temporary'): Promise<WardrobeItem> {
  const response = await request<any>(`/users/${encodeURIComponent(USER_ID)}/wardrobe`, {
    method: 'POST',
    body: JSON.stringify({ ...item, source: 'wardrobe', memory_type: memoryType, image_url: item.image_url ?? item.image ?? null }),
  })
  return { ...item, ...response, source: 'wardrobe' as const, memory_type: memoryType }
}

export async function updateWardrobeMemory(item: WardrobeItem, memoryType: 'temporary' | 'remembered'): Promise<WardrobeItem> {
  if (!item.id) return saveWardrobeItem(item, memoryType)
  const response = await request<any>(`/users/${encodeURIComponent(USER_ID)}/wardrobe/${encodeURIComponent(item.id)}`, {
    method: 'PUT',
    body: JSON.stringify({ ...item, source: 'wardrobe', memory_type: memoryType, image_url: item.image_url ?? item.image ?? null }),
  })
  return { ...item, ...response, source: 'wardrobe' as const, memory_type: memoryType }
}

export async function deleteSavedWardrobe(itemId: string): Promise<void> {
  await request(`/users/${encodeURIComponent(USER_ID)}/wardrobe/${encodeURIComponent(itemId)}`, { method: 'DELETE' })
}

export async function clearSavedWardrobe(): Promise<void> {
  await request(`/users/${encodeURIComponent(USER_ID)}/wardrobe`, { method: 'DELETE' })
}

const emptyProfile = (): StyleProfile => ({ shopping_fit: null, preferred_styles: [], preferred_colors: [], avoided_colors: [], usual_size: '', default_budget_per_outfit: null, preference_tags: [] })
export async function getStyleProfile(): Promise<StyleProfile> {
  const profile = await request<Partial<StyleProfile>>(`/users/${encodeURIComponent(USER_ID)}/profile`)
  return { ...emptyProfile(), ...profile, preferred_styles: profile.preferred_styles ?? [], preferred_colors: profile.preferred_colors ?? [], avoided_colors: profile.avoided_colors ?? [], preference_tags: profile.preference_tags ?? [] }
}
export async function saveStyleProfile(profile: StyleProfile): Promise<StyleProfile> {
  return request<StyleProfile>(`/users/${encodeURIComponent(USER_ID)}/profile`, { method: 'PUT', body: JSON.stringify(profile) })
}
export async function deleteStyleProfile(): Promise<void> {
  await request(`/users/${encodeURIComponent(USER_ID)}/profile`, { method: 'DELETE' })
}

export async function getLiveStatus(): Promise<LiveStatus> {
  const response = await fetch(`${API_BASE_URL}/health`)
  if (!response.ok) throw new Error(`Aura health ${response.status}`)
  const health = await response.json() as { vision_configured?: boolean; apify_configured?: boolean; cartesia_configured?: boolean; fetch_connected?: boolean }
  const fetchConnected = Boolean(health.fetch_connected)
  apiConfigured = response.ok && fetchConnected
  return { vision: Boolean(health.vision_configured), apify: Boolean(health.apify_configured), cartesia: Boolean(health.cartesia_configured), fetch: fetchConnected }
}

const normalizeSession = (payload: any): StyleSession => {
  if (payload?.parsedRequest && payload?.outfits && payload?.agentEvents) return payload as StyleSession
  const recommendation = payload?.final_recommendation ?? payload ?? {}
  const parsed = recommendation.parsed_request ?? {}
  const product = (item: any): Product => {
    const raw = item?.product ?? item?.wardrobe_item ?? item ?? {}
    const owned = item?.source_type === 'wardrobe' || item?.purchase_required === false || raw.owned === true
    return {
      id: String(item?.id ?? raw.id ?? crypto.randomUUID()), name: raw.name ?? 'Wardrobe item',
      retailer: owned ? 'Your wardrobe' : raw.retailer ?? 'Retailer', price: Number(raw.price ?? 0),
      category: raw.category ?? 'accessory', image: raw.image_url ?? raw.image ?? '',
      link: raw.product_url ?? raw.link ?? '', owned, source: owned ? 'wardrobe' : 'candidate',
      match: Number(item?.match_score ?? raw.match_score ?? (owned ? 100 : 0)), decision: item?.decision,
      note: raw.description,
    }
  }
  const event = (raw: any, index: number): AgentEvent => ({
    id: String(raw.id ?? `agent-${index}`), agent: String(raw.agent ?? 'orchestrator'),
    title: String(raw.type ?? 'agent_event').replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
    detail: String(raw.message ?? ''), status: raw.status === 'completed' ? 'done' : 'active',
  })
  const outfits: Outfit[] = (recommendation.outfits ?? []).map((raw: any, index: number) => {
    const breakdown = raw.score_breakdown ?? {}
    return {
      id: String(raw.id ?? `outfit-${index + 1}`), day: Number(raw.day ?? index + 1), title: raw.title ?? 'Planned look',
      setting: raw.occasion ?? raw.setting ?? 'Trip', score: Number(raw.match_score ?? raw.score ?? 0),
      scoreBreakdown: { style: Number(breakdown.style ?? 0), color: Number(breakdown.color ?? 0), occasion: Number(breakdown.occasion ?? 0), budget: Number(breakdown.budget ?? 0), preference: Number(breakdown.preference ?? 0) },
      products: (raw.items ?? raw.products ?? []).map(product), newSpend: Number(raw.new_purchase_cost ?? raw.newSpend ?? 0),
      whyItWorks: raw.why_it_works ?? raw.whyItWorks ?? '', accent: '#d88f68',
    }
  })
  const conflictRaw = payload?.conflict
  const conflict: SessionConflict | undefined = conflictRaw ? {
    status: String(conflictRaw.status ?? 'needs_user_input'), message: String(conflictRaw.message ?? 'This request needs a constraint choice.'),
    conflictingConstraints: conflictRaw.conflicting_constraints ?? [], options: conflictRaw.options ?? [],
  } : undefined
  const location = parsed.location ?? parsed.destination ?? 'Your trip'
  const days = Number(parsed.duration_days ?? parsed.days ?? outfits.length)
  return {
    session: String(recommendation.session_id ?? payload.session_id ?? `session-${Date.now()}`),
    parsedRequest: { destination: location, dates: parsed.dates ?? `${days} days`, days, aesthetic: [...new Set([...(parsed.preferred_colors ?? []), ...(parsed.styles ?? parsed.aesthetic ?? [])])].join(', '), outfits: Number(parsed.number_of_outfits ?? outfits.length), perOutfitBudget: Number(parsed.per_outfit_budget ?? 0), totalBudget: Number(parsed.total_budget ?? 0), required: (parsed.required_items ?? []).map((item: any) => item.item ?? item), avoid: parsed.avoid ?? [], owned: parsed.owned_item_references ?? [] },
    styleDNA: [], outfits, totalCost: Number(recommendation.total_new_purchase_cost ?? 0), newPurchaseCost: Number(recommendation.total_new_purchase_cost ?? 0),
    ownedItems: (recommendation.owned_items_used ?? []).map(product), reusedItems: (recommendation.reused_items ?? []).map(product),
    agentEvents: (recommendation.agent_events ?? []).map(event), constraintStatus: conflict?.status === 'needs_user_input' || recommendation.all_constraints_satisfied === false ? 'conflict' : 'satisfied', conflict,
    wardrobeReusedCount: Number(recommendation.wardrobe_reused_count ?? recommendation.reused_items?.length ?? 0),
    uniquePurchaseCount: Number(recommendation.unique_purchase_count ?? 0),
    purchasesAvoided: Number(recommendation.purchases_avoided ?? 0),
    wardrobeValueAvoided: Number(recommendation.wardrobe_value_avoided ?? 0),
    candidateReusedCount: Number(recommendation.candidate_reused_count ?? 0),
    profileVersion: recommendation.profile_version,
    profileSnapshot: recommendation.profile_snapshot,
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  })
  if (!response.ok) throw new Error(`Aura API ${response.status}: ${await response.text()}`)
  return response.json() as Promise<T>
}

const newSessionId = () => typeof crypto !== 'undefined' && crypto.randomUUID
  ? crypto.randomUUID()
  : `session-${Date.now()}`

export async function createStyleSession(prompt: string, sessionId = newSessionId(), wardrobe: WardrobeItem[] = [], profile?: StyleProfile): Promise<StyleSession> {
  console.debug('[Aura client] plan request inventory', { count: wardrobe.length, ids: wardrobe.map(item => item.id), categories: wardrobe.map(item => item.category), sources: wardrobe.map(item => item.source ?? 'wardrobe') })
  const payload = { raw_request: prompt, user_id: USER_ID, session_id: sessionId, wardrobe, profile }
  if ((import.meta as any).env?.DEV) {
    const safeWardrobe = wardrobe.map(({ image, image_url, ...item }) => item)
    console.debug('[Aura client] outgoing /shopping/plan payload', { ...payload, wardrobe: safeWardrobe })
  }
  const response = await request<any>('/shopping/plan', {
    method: 'POST',
    // Person 2's gateway forwards this request to Person 1 unchanged.
    body: JSON.stringify(payload),
  })
  const session = normalizeSession(response)
  if ((import.meta as any).env?.DEV) console.debug('[Aura client] /shopping/plan returned', { status: 'ok', looks: session.outfits.length, plannedSpend: session.newPurchaseCost, withinConstraints: session.constraintStatus === 'satisfied' })
  return session
}

export async function getStyleSession(sessionId: string): Promise<StyleSession> {
  return request<StyleSession>(`/api/style-sessions/${encodeURIComponent(sessionId)}`)
}

export async function modifyStyleSession(sessionId: string, instruction: string, wardrobe: WardrobeItem[] = [], profile?: StyleProfile): Promise<StyleSession> {
  const response = await request<any>('/shopping/modify', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, user_id: USER_ID, message: instruction, target_outfit_id: null, wardrobe, profile }),
  })
  return normalizeSession(response)
}

/** Cartesia stays server-side: the browser sends transcript text, never an API key. */
export async function sendVoiceTurn(sessionId: string, transcript: string, wardrobe: WardrobeItem[] = [], profile?: StyleProfile): Promise<VoiceAgentResponse> {
  // Voice must use the same single planning request and session as typed input.
  const styleSession = await createStyleSession(transcript, sessionId, wardrobe, profile)
  const response = await fetch(`${VOICE_API_BASE_URL}/api/voice-sessions/${encodeURIComponent(sessionId)}/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: `I found ${styleSession.outfits.length} looks for ${styleSession.parsedRequest.destination}. Your planned spend is $${styleSession.newPurchaseCost}.` }),
  }).then(async result => {
    if (!result.ok) throw new Error(`Aura voice API ${result.status}: ${await result.text()}`)
    return result.json() as Promise<{ session_id: string; audio_data_url?: string }>
  })
  return {
    sessionId: response.session_id,
    transcript,
    responseText: `I found ${styleSession.outfits.length} looks for ${styleSession.parsedRequest.destination}. Your planned spend is $${styleSession.newPurchaseCost}.`,
    state: 'ready',
    turns: [],
    agentEvents: styleSession.agentEvents,
    audioDataUrl: response.audio_data_url,
    styleSession,
  }
}

export async function speakVoiceResponse(sessionId: string, text: string): Promise<{ audioDataUrl?: string }> {
  const response = await fetch(`${VOICE_API_BASE_URL}/api/voice-sessions/${encodeURIComponent(sessionId)}/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) throw new Error(`Aura voice API ${response.status}: ${await response.text()}`)
  const result = await response.json() as { audio_data_url?: string }
  return { audioDataUrl: result.audio_data_url }
}

export async function transcribeVoiceAudio(sessionId: string, audio: Blob): Promise<{ transcript: string; model: string }> {
  const form = new FormData()
  form.append('audio', audio, 'voice.webm')
  const response = await fetch(`${VOICE_API_BASE_URL}/api/voice-sessions/${encodeURIComponent(sessionId)}/transcribe`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error(`Aura STT ${response.status}: ${await response.text()}`)
  const result = await response.json() as { transcript: string; model: string }
  return { transcript: result.transcript, model: result.model }
}

export async function analyzeWardrobeImage(file: File): Promise<WardrobeItem[]> {
  const form = new FormData()
  form.append('file', file, file.name)
  const response = await fetch(`${API_BASE_URL}/wardrobe/analyze`, { method: 'POST', body: form })
  if (!response.ok) throw new Error(await response.text())
  const result = await response.json() as { items?: WardrobeItem[] }
  return result.items ?? []
}

export async function compareWardrobeProduct(product: Record<string, unknown>, wardrobe: WardrobeItem[], budgetRemaining: number | null, perOutfitBudget?: number, totalBudget?: number, spentTotal?: number): Promise<ProductDecision> {
  const response = await request<ProductDecision>('/shopping/decision', {
    method: 'POST',
    body: JSON.stringify({ product, wardrobe, budget_remaining: budgetRemaining, per_outfit_budget: perOutfitBudget, total_budget: totalBudget, spent_total: spentTotal }),
  })
  return response
}

/** The shopping gateway creates sessions through /shopping/plan; it does not expose the old read endpoint. */
export async function loadDemoOrApiSession(): Promise<StyleSession> {
  return demoSession
}
