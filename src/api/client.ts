import { demoSession } from '../mockData'
import { StyleSession } from '../types'
import { VoiceAgentResponse } from '../voiceAgent'

/**
 * Backend adapter for the React layer.
 *
 * Keep API details here so components only deal with StyleSession objects.
 * With no VITE_API_BASE_URL, the app stays fully demoable against mock data.
 */
const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

export const apiConfigured = Boolean(API_BASE_URL)

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  })
  if (!response.ok) throw new Error(`Aura API ${response.status}: ${await response.text()}`)
  return response.json() as Promise<T>
}

export async function createStyleSession(prompt: string): Promise<StyleSession> {
  return request<StyleSession>('/api/style-sessions', {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  })
}

export async function getStyleSession(sessionId: string): Promise<StyleSession> {
  return request<StyleSession>(`/api/style-sessions/${encodeURIComponent(sessionId)}`)
}

export async function modifyStyleSession(sessionId: string, instruction: string): Promise<StyleSession> {
  return request<StyleSession>(`/api/style-sessions/${encodeURIComponent(sessionId)}/modifications`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  })
}

/** Cartesia stays server-side: the browser sends transcript text, never an API key. */
export async function sendVoiceTurn(sessionId: string, transcript: string): Promise<VoiceAgentResponse> {
  const response = await request<{
    session_id: string
    transcript: string
    response_text: string
    audio_data_url?: string
    agent_events?: unknown[]
  }>(`/api/voice-sessions/${encodeURIComponent(sessionId)}/turns`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, transcript }),
  })
  return {
    sessionId: response.session_id,
    transcript: response.transcript,
    responseText: response.response_text,
    state: 'ready',
    turns: [],
    agentEvents: response.agent_events,
    audioDataUrl: response.audio_data_url,
  }
}

/** Mock-first loader used during parallel backend development. */
export async function loadDemoOrApiSession(): Promise<StyleSession> {
  if (!apiConfigured) return demoSession
  return getStyleSession(demoSession.session)
}
