export type VoiceAgentState = 'idle' | 'listening' | 'heard' | 'thinking' | 'speaking' | 'error'

export interface VoiceTurn {
  id: string
  role: 'user' | 'assistant'
  text: string
  createdAt: string
  audioUrl?: string
}

export interface VoiceAgentResponse {
  sessionId: string
  transcript: string
  responseText: string
  state: 'ready' | 'planning' | 'error'
  turns: VoiceTurn[]
  agentEvents?: string[]
}
