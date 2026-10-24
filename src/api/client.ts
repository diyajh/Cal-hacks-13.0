import { demoSession } from '../mockData'
import { AgentEvent, Outfit, Product, SessionConflict, StyleSession } from '../types'
import { VoiceAgentResponse } from '../voiceAgent'

/**
 * Backend adapter for the React layer.
 *
 * Keep API details here so components only deal with StyleSession objects.
 * With no VITE_API_BASE_URL, the app stays fully demoable against mock data.
 */
const extensionRuntime = Boolean((globalThis as any).chrome?.runtime?.id)
const configuredBase = (import.meta as any).env?.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
const API_BASE_URL = configuredBase || (extensionRuntime ? 'http://127.0.0.1:8000' : '')
const VOICE_API_BASE_URL = (import.meta as any).env?.VITE_VOICE_API_BASE_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8018'
const USER_ID = (import.meta as any).env?.VITE_AURA_USER_ID || 'demo_user'

export const apiConfigured = Boolean(API_BASE_URL)

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
      link: raw.product_url ?? raw.link ?? '', owned, match: Number(item?.match_score ?? raw.match_score ?? (owned ? 100 : 0)),
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
    parsedRequest: { destination: location, dates: parsed.dates ?? `${days} days`, days, aesthetic: (parsed.styles ?? parsed.aesthetic ?? []).toString(), outfits: Number(parsed.number_of_outfits ?? outfits.length), perOutfitBudget: Number(parsed.per_outfit_budget ?? 0), totalBudget: Number(parsed.total_budget ?? 0), required: (parsed.required_items ?? []).map((item: any) => item.item ?? item), avoid: parsed.avoid ?? [], owned: parsed.owned_item_references ?? [] },
    styleDNA: [], outfits, totalCost: Number(recommendation.total_new_purchase_cost ?? 0), newPurchaseCost: Number(recommendation.total_new_purchase_cost ?? 0),
    ownedItems: (recommendation.owned_items_used ?? []).map(product), reusedItems: (recommendation.reused_items ?? []).map(product),
    agentEvents: (recommendation.agent_events ?? []).map(event), constraintStatus: conflict?.status === 'needs_user_input' || recommendation.all_constraints_satisfied === false ? 'conflict' : 'satisfied', conflict,
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

export async function createStyleSession(prompt: string, sessionId = newSessionId()): Promise<StyleSession> {
  const response = await request<any>('/shopping/plan', {
    method: 'POST',
    // Person 2's gateway forwards this request to Person 1 unchanged.
    body: JSON.stringify({ raw_request: prompt, user_id: USER_ID, session_id: sessionId }),
  })
  return normalizeSession(response)
}

export async function getStyleSession(sessionId: string): Promise<StyleSession> {
  return request<StyleSession>(`/api/style-sessions/${encodeURIComponent(sessionId)}`)
}

export async function modifyStyleSession(sessionId: string, instruction: string): Promise<StyleSession> {
  const response = await request<any>('/shopping/modify', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, user_id: USER_ID, message: instruction, target_outfit_id: null }),
  })
  return normalizeSession(response)
}

/** Cartesia stays server-side: the browser sends transcript text, never an API key. */
export async function sendVoiceTurn(sessionId: string, transcript: string): Promise<VoiceAgentResponse> {
  // Voice must use the same single planning request and session as typed input.
  const styleSession = await createStyleSession(transcript, sessionId)
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

/** Mock-first loader used during parallel backend development. */
export async function loadDemoOrApiSession(): Promise<StyleSession> {
  if (!apiConfigured) return demoSession
  try {
    return await getStyleSession(demoSession.session)
  } catch {
    // A fresh backend has no persisted demo session yet; keep the shell usable.
    return demoSession
  }
}
