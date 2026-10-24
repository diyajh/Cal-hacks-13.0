import { useEffect, useMemo, useState } from 'react'
import { demoSession } from './mockData'
import { Outfit, Product } from './types'
import { apiConfigured, createStyleSession, loadDemoOrApiSession, modifyStyleSession, sendVoiceTurn } from './api/client'
import { BrowserSpeechRecognition, createSpeechRecognition } from './voice'
import { VoiceAgentState, VoiceTurn } from './voiceAgent'

const money = (n: number) => `$${n}`
const demoVoiceRequest = "I'm going to San Diego for five days. I need five outfits under $50 each and my total budget under $500. I want a beachy neutral aesthetic. One outfit needs a crochet top and skirt. I already own white sneakers, so use them. I hate neon colors."

function ProductCard({ product }: { product: Product }) {
  return <div className="product-card">
    <div className="product-image" style={{ backgroundImage: `url(${product.image})` }}><span className={product.owned ? 'owned-pill' : 'retailer-pill'}>{product.owned ? '✓ In wardrobe' : product.retailer}</span></div>
    <div className="product-info"><div><span className="product-name">{product.name}</span><span className="product-retailer">{product.owned ? 'Already owned' : product.retailer}</span></div><strong>{product.owned ? '$0' : money(product.price)}</strong></div>
  </div>
}

function Score({ outfit }: { outfit: Outfit }) {
  return <div className="score-wrap"><div className="score-ring"><span>{outfit.score}</span><small>%</small></div><div><div className="eyebrow">MATCH SCORE</div><div className="score-bars">{Object.entries(outfit.scoreBreakdown).slice(0, 4).map(([label, value]) => <div className="score-row" key={label}><span>{label}</span><i><b style={{ width: `${value}%` }} /></i><em>{value}</em></div>)}</div></div></div>
}

function App() {
  const [session, setSession] = useState(demoSession)
  const [input, setInput] = useState('')
  const [modification, setModification] = useState('')
  const [activeDay, setActiveDay] = useState('all')
  const [isListening, setIsListening] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [checkoutOpen, setCheckoutOpen] = useState(false)
  const [apiError, setApiError] = useState('')
  const [voiceError, setVoiceError] = useState('')
  const [recognition, setRecognition] = useState<BrowserSpeechRecognition | null>(null)
  const [voiceState, setVoiceState] = useState<VoiceAgentState>('idle')
  const [voiceTranscript, setVoiceTranscript] = useState('')
  const [voiceTurns, setVoiceTurns] = useState<VoiceTurn[]>([])
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [memoryScope, setMemoryScope] = useState<'remembered' | 'temporary' | null>(null)
  const visibleOutfits = useMemo(() => activeDay === 'all' ? session.outfits : session.outfits.filter(o => String(o.day) === activeDay), [activeDay, session.outfits])
  useEffect(() => {
    if (!apiConfigured) return
    loadDemoOrApiSession().then(setSession).catch(() => setApiError('Live API unavailable — showing the demo plan.'))
  }, [])
  const submit = async () => {
    if (!input.trim()) return
    const prompt = input.trim()
    setSubmitted(true)
    setInput('')
    const isVoiceTurn = voiceState === 'heard' && Boolean(voiceTranscript)
    if (isVoiceTurn) {
      setVoiceState(apiConfigured ? 'thinking' : 'heard')
      if (apiConfigured) {
        try {
          const response = await sendVoiceTurn(session.session, prompt)
          const now = new Date().toISOString()
          setVoiceTurns(current => [...current, { id: `user-${Date.now()}`, role: 'user', text: prompt, createdAt: now }, { id: `assistant-${Date.now()}`, role: 'assistant', text: response.responseText, createdAt: now, audioUrl: response.audioDataUrl }])
          if (response.audioDataUrl) {
            const audio = new Audio(response.audioDataUrl)
            audio.onplay = () => { setIsSpeaking(true); setVoiceState('speaking') }
            audio.onended = () => { setIsSpeaking(false); setVoiceState('heard') }
            audio.onerror = () => { setIsSpeaking(false); setVoiceState('error'); setVoiceError('Aura received the response, but audio playback failed.') }
            await audio.play()
          } else {
            speakFallback(response.responseText)
          }
        } catch {
          setVoiceState('error')
          setVoiceError('Aura voice backend is unavailable. You can still type your request.')
        }
      } else {
        const responseText = 'I heard your San Diego trip brief. I’m checking your wardrobe, budget, and real product options now.'
        setVoiceTurns(current => [...current, { id: `user-${Date.now()}`, role: 'user', text: prompt, createdAt: new Date().toISOString() }, { id: `assistant-${Date.now()}`, role: 'assistant', text: responseText, createdAt: new Date().toISOString() }])
        speakFallback(responseText)
      }
    }
    if (apiConfigured) {
      try { setSession(await createStyleSession(prompt)) } catch { setApiError('Live API unavailable — showing the demo plan.') }
    }
  }
  const speakFallback = (text: string) => {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 1.02
    utterance.onstart = () => { setIsSpeaking(true); setVoiceState('speaking') }
    utterance.onend = () => { setIsSpeaking(false); setVoiceState('heard') }
    window.speechSynthesis.speak(utterance)
  }
  const stopSpeaking = () => {
    window.speechSynthesis?.cancel()
    setIsSpeaking(false)
    setVoiceState('heard')
  }
  const toggleVoice = () => {
    if (isListening) {
      recognition?.stop()
      setVoiceState('heard')
      return
    }
    const nextRecognition = createSpeechRecognition()
    if (!nextRecognition) {
      setVoiceState('error')
      setVoiceError('Voice input is not supported in this browser. You can still type your request.')
      return
    }
    setVoiceError('')
    setVoiceState('listening')
    nextRecognition.onresult = event => {
      const transcript = event.results[0]?.[0]?.transcript ?? ''
      setVoiceTranscript(transcript)
      setVoiceState('heard')
      setInput(current => `${current}${current ? ' ' : ''}${transcript}`)
    }
    nextRecognition.onend = () => { setIsListening(false); setVoiceState(current => current === 'listening' ? 'heard' : current) }
    nextRecognition.onerror = () => {
      setIsListening(false)
      setVoiceState('error')
      setVoiceError('Aura could not hear that. Please try again or type your request.')
    }
    setRecognition(nextRecognition)
    setIsListening(true)
    nextRecognition.start()
  }
  const useDemoVoice = () => {
    setInput(demoVoiceRequest)
    setVoiceTranscript(demoVoiceRequest)
    setVoiceError('')
    setVoiceState('heard')
  }
  const applyModification = () => {
    if (!modification.trim()) return
    const text = modification.toLowerCase()
    const instruction = modification.trim()
    if (apiConfigured) {
      setModification('')
      modifyStyleSession(session.session, instruction).then(setSession).catch(() => setApiError('Live API unavailable — showing the demo plan.'))
      setSubmitted(true)
      return
    }
    const targetsDayThree = text.includes('three') || text.includes('3') || text.includes('golden hour')
    if (targetsDayThree && (text.includes('elegant') || text.includes('hate') || text.includes('replace'))) {
      setSession(current => ({ ...current, outfits: current.outfits.map(outfit => outfit.day === 3 ? {
        ...outfit,
        title: 'Golden hour, refined',
        score: 98,
        scoreBreakdown: { ...outfit.scoreBreakdown, style: 100, occasion: 98, preference: 96 },
        whyItWorks: 'I kept the easy sneaker base, then elevated the silhouette with a cleaner line and a more polished sunset-ready finish.',
      } : outfit), agentEvents: [...current.agentEvents.slice(0, -1), { id: `e${Date.now()}`, agent: 'OUTFIT PLANNER', title: 'Day 3 replanned', detail: 'Elegant alternative accepted · 98% match', status: 'active' as const }] }))
      setSubmitted(true)
      setModification('')
      setActiveDay('3')
      return
    }
    setSubmitted(true)
    setModification('')
  }
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">a</span><span>AURA</span></div><div className="side-label">YOUR SPACE</div><nav><button className="nav-active">✦ <span>Style agent</span></button><button>◌ <span>My wardrobe</span><span className="nav-count">3</span></button><button>♡ <span>Saved looks</span></button></nav><div className="sidebar-bottom"><div className="avatar">JM</div><div><strong>Jordan M.</strong><span>Style DNA · 4 traits</span></div><button className="more">•••</button></div></aside>
    <main className="main"><header className="topbar"><div><div className="eyebrow">YOUR PERSONAL SHOPPING AGENT</div><h1>Good morning, Jordan <span>✦</span></h1></div><div className="header-actions"><button className="icon-btn">?</button><button className="profile-btn">JM <span>⌄</span></button></div></header>
      <section className="hero"><div className="hero-copy"><span className="kicker">PLAN A LOOK</span><h2>Where are we going?</h2><p>Tell me the occasion, your mood, and any constraints. I’ll handle the rest.</p><div className="prompt-box"><textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder="e.g. Five beachy outfits for San Diego under $50 each..." /><div className="prompt-actions"><button className={isListening ? 'mic listening' : 'mic'} onClick={toggleVoice}>{isListening ? '● Listening…' : '◉ Voice input'}</button><button className="send" onClick={submit}>Plan my looks <span>→</span></button></div>{voiceError && <div className="voice-error"><span>{voiceError}</span><button onClick={useDemoVoice}>Use demo transcript</button></div>}</div><div className="suggestions"><span>Try a prompt</span><button onClick={() => setInput('I need a dinner look for Friday under $150')}>Dinner date</button><button onClick={() => setInput('Build me a capsule wardrobe for fall')}>Fall capsule</button></div></div><div className="dna-card"><div className="dna-top"><span className="kicker">YOUR STYLE DNA</span><button>View profile →</button></div><div className="dna-visual"><div className="dna-donut"><span>4<br/><small>traits</small></span></div><div className="dna-legend">{session.styleDNA.map(s => <div key={s.label}><i style={{ background: s.color }} /><span>{s.label}</span><strong>{s.value}%</strong></div>)}</div></div><p>Soft structure, sun-washed color, and pieces that can move with you.</p></div></section>
      {submitted && <div className="toast">{apiError || 'Got it — updating your plan with that request.'}</div>}
      {voiceState !== 'idle' && <div className={`voice-agent-strip ${voiceState}`}><div className="voice-orb">{voiceState === 'listening' ? '◉' : voiceState === 'error' ? '!' : voiceState === 'speaking' ? '♫' : '✦'}</div><div><span className="eyebrow">AURA VOICE AGENT</span><strong>{voiceState === 'listening' ? 'Listening for your trip brief…' : voiceState === 'heard' ? 'I heard your request' : voiceState === 'error' ? 'Voice input needs a retry' : voiceState === 'speaking' ? 'Aura is speaking…' : 'Voice session ready'}</strong>{voiceTranscript && <p>“{voiceTranscript}”</p>}</div>{isSpeaking ? <button className="stop-speaking" onClick={stopSpeaking}>Stop speaking</button> : <span className="voice-provider">{apiConfigured ? 'Ink STT · Sonic TTS' : 'Browser fallback · Cartesia-ready'}</span>}</div>}
      {voiceTurns.length > 0 && <div className="voice-turn-card"><div className="voice-turn-head"><span className="eyebrow">VOICE SESSION</span><span>2 turns · transcript saved to this session</span></div>{voiceTurns.slice(-2).map(turn => <div className={`voice-turn ${turn.role}`} key={turn.id}><span>{turn.role === 'user' ? 'YOU' : 'AURA'}</span><p>{turn.text}</p></div>)}</div>}
      <section className="workspace"><div className="section-heading"><div><span className="kicker">LIVE SESSION</span><h2>San Diego, in style <span className="live-dot" /></h2></div><button className="ghost-btn">↗ Share plan</button></div><div className="understood"><div className="understood-head"><div><span className="eyebrow">I UNDERSTOOD</span><h3>5 days by the coast <button className="edit-btn">Edit</button></h3></div><span className="check">✓ Constraints satisfied</span></div><div className="chips"><span>◉ <b>Aug 14 – 18</b></span><span>✦ <b>Beachy / neutral</b></span><span>♧ <b>5 outfits</b></span><span>⌖ <b>$50 / outfit</b></span><span>◌ <b>Under $500 total</b></span><span className="muted-chip">Avoids neon</span><span className="muted-chip">Uses white sneakers</span></div></div>
        <div className="agent-grid"><div className="activity"><div className="activity-head"><div><span className="eyebrow">AURA IS WORKING</span><h3>Making the fit happen</h3></div><span className="pulse">● Live</span></div><div className="timeline">{session.agentEvents.map((event, i) => <div className={`event ${event.status}`} key={event.id}><div className="event-line"><span className="event-dot">{event.status === 'done' ? '✓' : '✦'}</span>{i < session.agentEvents.length - 1 && <i />}</div><div className="event-copy"><span>{event.agent}</span><strong>{event.title}</strong><p>{event.detail}</p></div></div>)}</div></div><div className="wardrobe-card"><span className="eyebrow">WARDROBE REUSE</span><h3>Already in your closet</h3><div className="reuse-item"><div className="tiny-shoe" style={{ backgroundImage: `url(${session.ownedItems[0].image})` }} /><div><strong>White sneakers</strong><span>Used in 3 looks</span></div><b>$0</b></div><div className="save-line"><span>Saved through reuse</span><strong>$72</strong></div>{memoryScope ? <div className="memory-confirmed">✓ {memoryScope === 'remembered' ? 'Remembered until you remove it' : 'Temporary for this trip · expires in 30 days'}</div> : <div className="memory-controls"><span>Remember this item?</span><div><button onClick={() => setMemoryScope('remembered')}>Remember</button><button onClick={() => setMemoryScope('temporary')}>Temporary</button></div></div>}<button className="text-btn">Manage wardrobe →</button></div></div>
      </section>
      <section className="looks"><div className="looks-head"><div><span className="kicker">YOUR EDIT</span><h2>Five looks, one easy trip</h2><p>Ranked for your style, plans, and budget. <button className="text-btn">Why these?</button></p></div><div className="total-card"><span>NEW PURCHASES</span><strong>$228 <small>/ $500</small></strong><div className="progress"><i /></div><em>Well within budget</em></div></div><div className="day-tabs"><button className={activeDay === 'all' ? 'selected' : ''} onClick={() => setActiveDay('all')}>All looks <span>5</span></button>{[1,2,3,4,5].map(d => <button className={activeDay === String(d) ? 'selected' : ''} key={d} onClick={() => setActiveDay(String(d))}>Day {d}</button>)}</div><div className="outfit-list">{visibleOutfits.map(outfit => <article className="outfit-card" key={outfit.id}><div className="outfit-top"><div className="day-badge">DAY {outfit.day}</div><div><h3>{outfit.title}</h3><p>{outfit.setting}</p></div><Score outfit={outfit} /><button className="save">♡</button></div><div className="product-grid">{outfit.products.map(product => <ProductCard product={product} key={product.id} />)}</div><div className="outfit-footer"><p><span>WHY THIS WORKS</span>{outfit.whyItWorks}</p><div className="outfit-cost"><span>NEW SPEND</span><strong>${outfit.newSpend}</strong></div><button className="detail-btn">See details →</button></div></article>)}</div><div className="more-looks"><span>+ 2 more looks ready</span><button onClick={() => setActiveDay('all')}>Show full trip <span>↓</span></button></div></section>
      <section className="modification-bar"><div><span className="eyebrow">KEEP EXPLORING</span><strong>Want to change something?</strong><p>Aura will replan only the pieces affected by your note.</p></div><div className="modification-input"><input value={modification} onChange={e => setModification(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') applyModification() }} placeholder="Try: Make outfit three more elegant" /><button onClick={applyModification}>Update plan <span>→</span></button></div></section>
      <footer className="checkout-bar"><div><span className="eyebrow">YOUR SHORTLIST</span><strong>12 pieces <small>· 3 from your wardrobe</small></strong></div><div className="checkout-total"><span>Total</span><strong>$228</strong></div><button className="checkout-btn" onClick={() => setCheckoutOpen(true)}>Continue to checkout <span>→</span></button></footer>
      {checkoutOpen && <div className="modal-backdrop" onClick={() => setCheckoutOpen(false)}><div className="checkout-modal" onClick={e => e.stopPropagation()}><button className="modal-close" onClick={() => setCheckoutOpen(false)}>×</button><span className="kicker">READY WHEN YOU ARE</span><h2>Your San Diego edit</h2><p className="modal-subtitle">Everything you selected, with your closet doing some of the work.</p><div className="checkout-summary"><div><span>LOOKS</span><strong>5</strong></div><div><span>PIECES</span><strong>12</strong></div><div><span>WARDROBE</span><strong>3 reused</strong></div><div><span>NEW SPEND</span><strong>$228</strong></div></div><div className="selected-list"><div className="selected-row"><div className="mini-product" style={{ backgroundImage: `url(${session.outfits[0].products[0].image})` }} /><div><strong>New pieces to purchase</strong><span>7 items across 5 looks</span></div><b>$228</b></div><div className="selected-row reused"><div className="mini-product" style={{ backgroundImage: `url(${session.ownedItems[0].image})` }} /><div><strong>White leather sneakers</strong><span>Already in your wardrobe · used 3×</span></div><b>$0</b></div></div><div className="privacy-note"><span>♧</span><p><strong>Your privacy matters.</strong> Aura does not store payment-card details. Temporary trip preferences expire after 30 days; remembered wardrobe items stay until you remove them.</p></div><button className="visa-btn" onClick={() => setCheckoutOpen(false)}>Checkout with Visa <span>→</span></button><button className="back-btn" onClick={() => setCheckoutOpen(false)}>Back to edit</button></div></div>}
    </main>
  </div>
}
export default App
