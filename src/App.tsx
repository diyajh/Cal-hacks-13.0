import { CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { demoSession } from './mockData'
import { Outfit, Product } from './types'
import { apiConfigured, createStyleSession, loadDemoOrApiSession, modifyStyleSession, sendVoiceTurn, transcribeVoiceAudio } from './api/client'
import { BrowserSpeechRecognition, createSpeechRecognition } from './voice'
import { VoiceAgentState, VoiceTurn } from './voiceAgent'
import { addPageContext, getActivePageContext } from './extensionBridge'

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

function EditorialStage({ session, onProduct, onOutfit, onPlan }: { session: typeof demoSession; onProduct: (product: Product) => void; onOutfit: (outfit: Outfit) => void; onPlan: () => void }) {
  const stageRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const move = (event: PointerEvent) => {
      const bounds = stage.getBoundingClientRect()
      stage.style.setProperty('--px', `${((event.clientX - bounds.left) / bounds.width - 0.5) * 16}px`)
      stage.style.setProperty('--py', `${((event.clientY - bounds.top) / bounds.height - 0.5) * 12}px`)
    }
    const reset = () => { stage.style.setProperty('--px', '0px'); stage.style.setProperty('--py', '0px') }
    stage.addEventListener('pointermove', move)
    stage.addEventListener('pointerleave', reset)
    return () => { stage.removeEventListener('pointermove', move); stage.removeEventListener('pointerleave', reset) }
  }, [])
  const products = Array.from(new Map(session.outfits.flatMap(outfit => outfit.products).map(product => [product.id, product])).values()).slice(0, 9)
  return <section ref={stageRef} className="editorial-stage" aria-label="Aura editorial recommendation stage">
    <div className="stage-heading"><span>AURA — PERSONAL SHOPPING AGENT</span><small>{session.parsedRequest.destination || 'Your trip'} · {session.outfits.length} looks</small></div>
    <div className="stage-wordmark" aria-hidden="true">AURA</div>
    <div className="stage-subtitle">Your wardrobe, interpreted.</div>
    {products.map((product, index) => <button className={`floating-product depth-${index % 4}`} key={product.id} onClick={() => onProduct(product)} style={{ '--x': `${8 + ((index * 31) % 84)}%`, '--y': `${17 + ((index * 19) % 64)}%`, '--r': `${-9 + (index % 5) * 5}deg`, '--parallax': `${0.45 + (index % 4) * 0.2}` } as CSSProperties} aria-label={`Inspect ${product.name}`}><span className="floating-image" style={{ backgroundImage: product.image ? `url(${product.image})` : undefined }} /><span className="floating-label">{product.name}<small>{product.owned ? 'In wardrobe' : `${product.retailer} · $${product.price}`}</small></span></button>)}
    <div className="stage-outfits">{session.outfits.slice(0, 5).map(outfit => <button key={outfit.id} onClick={() => onOutfit(outfit)}>Day {outfit.day} · {outfit.title}</button>)}</div>
    <div className="stage-control"><span className="eyebrow">AURA IS WORKING</span><strong>{session.agentEvents[session.agentEvents.length - 1]?.title || 'Plan ready'}</strong><p>{session.agentEvents[session.agentEvents.length - 1]?.detail || 'Explore a piece or outfit to see the reasoning.'}</p><div><span>{session.newPurchaseCost ? `$${session.newPurchaseCost} planned` : 'Budget ready'}</span><button onClick={onPlan}>Smart purchase plan →</button></div></div>
    <span className="stage-instruction">Click a piece or outfit to inspect</span>
  </section>
}

function DecisionOverlay({ product, outfit, onClose }: { product: Product | null; outfit: Outfit | null; onClose: () => void }) {
  if (!product && !outfit) return null
  return <div className="decision-backdrop" onClick={onClose}><div className="decision-panel" onClick={event => event.stopPropagation()}><button className="decision-close" onClick={onClose}>×</button>{product ? <><span className="eyebrow">PRODUCT DECISION</span><h2>{product.name}</h2><p className="decision-meta">{product.owned ? 'Already in your wardrobe' : `${product.retailer} · $${product.price}`}</p><div className="decision-image" style={{ backgroundImage: product.image ? `url(${product.image})` : undefined }} /><div className="decision-facts"><span>{product.owned ? 'WARDROBE ITEM' : 'NEW PURCHASE'}<strong>{product.owned ? '$0 additional cost' : `$${product.price} planned spend`}</strong></span><span>MATCH<strong>{product.match || '—'} / 100</strong></span></div><p className="decision-copy">{product.owned ? 'Aura reused this piece to avoid an unnecessary purchase and keep the look compatible with your existing wardrobe.' : `Aura selected this ${product.category} because it fits the requested style and budget. It is included in the smart purchase plan.`}</p>{!product.owned && product.link && <a className="decision-link" href={product.link} target="_blank" rel="noreferrer">View at retailer →</a>}</> : <><span className="eyebrow">OUTFIT REASONING</span><h2>{outfit?.title}</h2><p className="decision-meta">Day {outfit?.day} · {outfit?.setting} · {outfit?.score}% match</p><p className="decision-copy">{outfit?.whyItWorks}</p><div className="decision-facts"><span>NEW SPEND<strong>${outfit?.newSpend}</strong></span><span>PIECES<strong>{outfit?.products.length}</strong></span></div></>}</div></div>
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
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null)
  const audioChunks = useRef<Blob[]>([])
  const [voiceState, setVoiceState] = useState<VoiceAgentState>('idle')
  const [voiceTranscript, setVoiceTranscript] = useState('')
  const [voiceTurns, setVoiceTurns] = useState<VoiceTurn[]>([])
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [memoryScope, setMemoryScope] = useState<'remembered' | 'temporary' | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [selectedOutfit, setSelectedOutfit] = useState<Outfit | null>(null)
  const extensionRuntime = Boolean((globalThis as any).chrome?.runtime?.id)
  const cartesiaConfigured = Boolean((import.meta as any).env?.VITE_VOICE_API_BASE_URL || 'http://127.0.0.1:8018')
  const visibleOutfits = useMemo(() => activeDay === 'all' ? session.outfits : session.outfits.filter(o => String(o.day) === activeDay), [activeDay, session.outfits])
  const wardrobeItem = session.ownedItems[0]
  const request = session.parsedRequest
  const purchaseItems = Array.from(new Map(session.outfits.flatMap(outfit => outfit.products).filter(product => !product.owned).map(product => [product.id, product])).values())
  const totalPieces = session.outfits.reduce((total, outfit) => total + outfit.products.length, 0)
  const reusedPieces = session.outfits.flatMap(outfit => outfit.products).filter(product => product.owned).length
  const uniqueWardrobeItems = new Set(session.outfits.flatMap(outfit => outfit.products).filter(product => product.owned).map(product => product.id)).size
  const remainingBudget = Math.max((request.totalBudget || 0) - session.newPurchaseCost, 0)
  const tripLabel = request.destination || 'your trip'
  useEffect(() => {
    if (!apiConfigured) return
    loadDemoOrApiSession().then(setSession).catch(() => setApiError('Live API unavailable — showing the demo plan.'))
  }, [])
  const submit = async () => {
    if (!input.trim()) return
    const prompt = addPageContext(input.trim(), await getActivePageContext())
    setSubmitted(true)
    setInput('')
    const isVoiceTurn = voiceState === 'heard' && Boolean(voiceTranscript)
    if (isVoiceTurn) {
      setVoiceState(apiConfigured ? 'thinking' : 'heard')
      if (apiConfigured) {
        try {
          const response = await sendVoiceTurn(session.session, prompt)
          if (response.styleSession) setSession(response.styleSession)
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
    if (apiConfigured && !isVoiceTurn) {
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
  const toggleVoice = async () => {
    if (isListening) {
      if (cartesiaConfigured) {
        mediaRecorder?.stop()
      } else {
        recognition?.stop()
        setVoiceState('heard')
      }
      return
    }
    if (cartesiaConfigured) {
      if (!navigator.mediaDevices?.getUserMedia || !('MediaRecorder' in window)) {
        setVoiceState('error')
        setVoiceError('Live microphone recording is not supported here. You can still type your request.')
        return
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const recorder = new MediaRecorder(stream)
        audioChunks.current = []
        recorder.ondataavailable = event => { if (event.data.size > 0) audioChunks.current.push(event.data) }
        recorder.onstop = async () => {
          stream.getTracks().forEach(track => track.stop())
          setMediaRecorder(null)
          setIsListening(false)
          setVoiceState('thinking')
          try {
            const blob = new Blob(audioChunks.current, { type: recorder.mimeType || 'audio/webm' })
            const result = await transcribeVoiceAudio(session.session, blob)
            setVoiceTranscript(result.transcript)
            setInput(current => `${current}${current ? ' ' : ''}${result.transcript}`)
            setVoiceState('heard')
          } catch {
            setVoiceState('error')
            setVoiceError('Aura could not transcribe that recording. Please try again or type your request.')
          }
        }
        recorder.start()
        setMediaRecorder(recorder)
        setVoiceError('')
        setVoiceState('listening')
        setIsListening(true)
      } catch {
        setVoiceState('error')
        setVoiceError('Microphone permission was denied. You can still type your request.')
      }
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
  const resolveConflict = async (option: string | { label?: string; value?: string; message?: string }) => {
    const message = typeof option === 'string' ? option : option.message ?? option.label ?? option.value ?? ''
    if (!message) return
    setSubmitted(true)
    try { setSession(await modifyStyleSession(session.session, message)) } catch { setApiError('Could not resolve that constraint yet. Please try again.') }
  }
  if (extensionRuntime) return <div className="extension-shell">
    <header className="extension-header"><div className="extension-brand"><span className="brand-mark">a</span><strong>AURA</strong></div><span className="extension-status"><i />{submitted ? 'Plan active' : 'Ready'}</span></header>
    <main className="extension-main">
      <section className="extension-request">
        <span className="eyebrow">PERSONAL SHOPPING AGENT</span>
        <h1>What are you planning?</h1>
        <p className="extension-hint">Tell Aura where you’re going, what you need, and your limits.</p>
        <div className="extension-input-wrap"><textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder="e.g. Five beachy outfits for San Diego under $50 each" /><div className="extension-input-actions"><button className={isListening ? 'mic listening' : 'mic'} onClick={toggleVoice}>{isListening ? '● Listening…' : '◉ Voice'}</button><button className="extension-primary" onClick={submit}>Plan <span>→</span></button></div>{voiceError && <div className="voice-error"><span>{voiceError}</span><button onClick={useDemoVoice}>Use demo transcript</button></div>}</div>
        {!input && <div className="extension-suggestions"><button onClick={() => setInput('I need a dinner look for Friday under $150')}>Dinner date</button><button onClick={() => setInput('Build me a capsule wardrobe for fall')}>Fall capsule</button></div>}
      </section>
      {submitted && <section className="extension-brief"><div><span className="eyebrow">CURRENT BRIEF</span><strong>{tripLabel}</strong><p>{request.days || session.outfits.length} days · {request.aesthetic || 'Personalized style'} · {session.outfits.length} looks</p></div><span className={session.constraintStatus === 'satisfied' ? 'extension-check' : 'extension-conflict'}>{session.constraintStatus === 'satisfied' ? '✓ Within constraints' : 'Needs review'}</span></section>}
      {session.conflict?.status === 'needs_user_input' && <div className="extension-conflict-card"><span className="eyebrow">AURA NEEDS A CHOICE</span><strong>{session.conflict.message}</strong><div>{session.conflict.options.map((option, index) => <button key={index} onClick={() => resolveConflict(option)}>{typeof option === 'string' ? option : option.label ?? option.message ?? option.value}</button>)}</div></div>}
      {submitted && <section className="extension-activity"><div className="extension-section-head"><div><span className="eyebrow">AGENT ACTIVITY</span><strong>{session.agentEvents[session.agentEvents.length - 1]?.title || 'Plan ready'}</strong></div><span className="extension-live"><i /> live</span></div><div className="extension-events">{session.agentEvents.slice(-4).map(event => <div className="extension-event" key={event.id}><span className={event.status === 'done' ? 'event-done' : 'event-current'}>{event.status === 'done' ? '✓' : '•'}</span><div><b>{event.agent}</b><span>{event.title}</span><small>{event.detail}</small></div></div>)}</div></section>}
      {submitted && <section className="extension-plan"><div className="extension-section-head"><div><span className="eyebrow">YOUR PLAN</span><strong>{session.outfits.length} ranked looks</strong></div><span className="extension-spend">${session.newPurchaseCost} planned</span></div><div className="extension-look-list">{visibleOutfits.slice(0, 5).map(outfit => <article className="extension-look" key={outfit.id} onClick={() => { setSelectedProduct(null); setSelectedOutfit(outfit) }}><div className="extension-look-top"><span className="extension-day">DAY {outfit.day}</span><div><strong>{outfit.title}</strong><small>{outfit.setting}</small></div><span className="extension-score">{outfit.score}%</span></div><div className="extension-products">{outfit.products.slice(0, 3).map(product => <button key={product.id} onClick={event => { event.stopPropagation(); setSelectedOutfit(null); setSelectedProduct(product) }}><span style={{ backgroundImage: product.image ? `url(${product.image})` : undefined }} /><b>{product.name}</b><small>{product.owned ? 'In wardrobe' : `$${product.price}`}</small></button>)}</div><p><b>Why:</b> {outfit.whyItWorks}</p></article>)}</div></section>}
      {submitted && <section className="extension-reuse"><div><span className="eyebrow">WARDROBE REUSE</span><strong>{reusedPieces} pieces reused · ${remainingBudget} left</strong><p>{wardrobeItem?.name ?? 'No saved wardrobe items'} {wardrobeItem ? 'was reused to avoid an unnecessary purchase.' : 'Add items to help Aura save more.'}</p></div><span className="extension-zero">$0</span></section>}
      {submitted && <section className="extension-modify"><span className="eyebrow">REFINE THE PLAN</span><div><input value={modification} onChange={e => setModification(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') applyModification() }} placeholder="Replace the skirt in outfit 3…" /><button onClick={applyModification}>Update</button></div></section>}
    </main>
    {submitted && <footer className="extension-footer"><div><span className="eyebrow">SMART PURCHASE PLAN</span><strong>{purchaseItems.length} items to buy · {reusedPieces} reused</strong></div><button onClick={() => setCheckoutOpen(true)}>Review plan <span>→</span></button></footer>}
    <DecisionOverlay product={selectedProduct} outfit={selectedOutfit} onClose={() => { setSelectedProduct(null); setSelectedOutfit(null) }} />
    {checkoutOpen && <div className="modal-backdrop" onClick={() => setCheckoutOpen(false)}><div className="checkout-modal" onClick={e => e.stopPropagation()}><button className="modal-close" onClick={() => setCheckoutOpen(false)}>×</button><span className="kicker">SMART PURCHASE PLAN</span><h2>{tripLabel}</h2><p className="modal-subtitle">Real products to consider. No payment details are collected.</p><div className="checkout-summary"><div><span>OUTFITS</span><strong>{session.outfits.length}</strong></div><div><span>PIECES</span><strong>{totalPieces}</strong></div><div><span>REUSED</span><strong>{reusedPieces}</strong></div><div><span>TO BUY</span><strong>{purchaseItems.length}</strong></div></div><div className="budget-summary"><span>Budget ${request.totalBudget || 0}</span><strong>${session.newPurchaseCost} planned · ${remainingBudget} remaining</strong></div><div className="selected-list">{purchaseItems.map(product => <div className="selected-row" key={product.id}><div className="mini-product" style={{ backgroundImage: `url(${product.image})` }} /><div><strong>{product.name}</strong><span>{product.retailer} · ${product.price}</span></div><a className="merchant-link" href={product.link} target="_blank" rel="noreferrer">View product →</a></div>)}</div><div className="privacy-note"><span>♧</span><p><strong>Trust by design.</strong> Aura never stores payment-card details.</p></div></div></div>}
  </div>
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">a</span><span>AURA</span></div><div className="side-label">YOUR SPACE</div><nav><button className="nav-active">✦ <span>Style agent</span></button><button>◌ <span>My wardrobe</span><span className="nav-count">3</span></button><button>♡ <span>Saved looks</span></button></nav><div className="sidebar-bottom"><div className="avatar">JM</div><div><strong>Jordan M.</strong><span>Style DNA · 4 traits</span></div><button className="more">•••</button></div></aside>
    <main className="main"><header className="topbar"><div><div className="eyebrow">YOUR PERSONAL SHOPPING AGENT</div><h1>Good morning, Jordan <span>✦</span></h1></div><div className="header-actions"><button className="profile-btn">JM <span>⌄</span></button></div></header>
      <section className="hero"><div className="hero-copy"><span className="kicker">PLAN A LOOK</span><h2>Where are we going?</h2><p>Tell me the occasion, your mood, and any constraints. I’ll handle the rest.</p><div className="prompt-box"><textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder="e.g. Five beachy outfits for San Diego under $50 each..." /><div className="prompt-actions"><button className={isListening ? 'mic listening' : 'mic'} onClick={toggleVoice}>{isListening ? '● Listening…' : '◉ Voice input'}</button><button className="send" onClick={submit}>Plan my looks <span>→</span></button></div>{voiceError && <div className="voice-error"><span>{voiceError}</span><button onClick={useDemoVoice}>Use demo transcript</button></div>}</div><div className="suggestions"><span>Try a prompt</span><button onClick={() => setInput('I need a dinner look for Friday under $150')}>Dinner date</button><button onClick={() => setInput('Build me a capsule wardrobe for fall')}>Fall capsule</button></div></div><div className="dna-card"><div className="dna-top"><span className="kicker">YOUR STYLE DNA</span><button>View profile →</button></div><div className="dna-visual"><div className="dna-donut"><span>4<br/><small>traits</small></span></div><div className="dna-legend">{session.styleDNA.map(s => <div key={s.label}><i style={{ background: s.color }} /><span>{s.label}</span><strong>{s.value}%</strong></div>)}</div></div><p>Soft structure, sun-washed color, and pieces that can move with you.</p></div></section>
      <EditorialStage session={session} onProduct={product => { setSelectedOutfit(null); setSelectedProduct(product) }} onOutfit={outfit => { setSelectedProduct(null); setSelectedOutfit(outfit) }} onPlan={() => setCheckoutOpen(true)} />
      <DecisionOverlay product={selectedProduct} outfit={selectedOutfit} onClose={() => { setSelectedProduct(null); setSelectedOutfit(null) }} />
      <section className="workspace"><div className="section-heading"><div><span className="kicker">LIVE SESSION</span><h2>{tripLabel}, in style <span className="live-dot" /></h2></div><button className="ghost-btn">↗ Share plan</button></div><div className="understood"><div className="understood-head"><div><span className="eyebrow">I UNDERSTOOD</span><h3>{request.days || session.outfits.length} days · {request.aesthetic || 'your style'} <button className="edit-btn">Edit</button></h3></div><span className={session.constraintStatus === 'satisfied' ? 'check' : 'check conflict'}>{session.constraintStatus === 'satisfied' ? '✓ Constraints satisfied' : '⚠ Needs a constraint review'}</span></div><div className="chips"><span>◉ <b>{request.dates || `${request.days || session.outfits.length} days`}</b></span><span>✦ <b>{request.aesthetic || 'Personalized style'}</b></span><span>♧ <b>{request.outfits || session.outfits.length} outfits</b></span><span>⌖ <b>${request.perOutfitBudget || 0} / outfit</b></span><span>◌ <b>Under ${request.totalBudget || 0} total</b></span>{request.avoid.map(item => <span className="muted-chip" key={item}>Avoids {item}</span>)}{request.owned.map(item => <span className="muted-chip" key={item}>Uses {item}</span>)}</div></div>
        {session.conflict?.status === 'needs_user_input' && <div className="conflict-card"><span className="eyebrow">AURA NEEDS A CHOICE</span><h3>{session.conflict.message}</h3><p>{session.conflict.conflictingConstraints.join(' · ')}</p><div>{session.conflict.options.map((option, index) => <button key={index} onClick={() => resolveConflict(option)}>{typeof option === 'string' ? option : option.label ?? option.message ?? option.value}</button>)}</div></div>}
        <div className="agent-grid"><div className="activity"><div className="activity-head"><div><span className="eyebrow">AURA IS WORKING</span><h3>Real agent reasoning</h3></div><span className="pulse">● Live</span></div><div className="timeline">{session.agentEvents.map((event, i) => <div className={`event ${event.status}`} key={event.id}><div className="event-line"><span className="event-dot">{event.status === 'done' ? '✓' : '✦'}</span>{i < session.agentEvents.length - 1 && <i />}</div><div className="event-copy"><span>{event.agent}</span><strong>{event.title}</strong><p>{event.detail}</p></div></div>)}</div></div><div className="wardrobe-card"><span className="eyebrow">WARDROBE REUSE</span><h3>Measurable savings</h3><div className="reuse-item"><div className="tiny-shoe" style={wardrobeItem ? { backgroundImage: `url(${wardrobeItem.image})` } : undefined} /><div><strong>{wardrobeItem?.name ?? 'No saved wardrobe item'}</strong><span>{wardrobeItem ? `Already owned · used across ${reusedPieces} look pieces` : 'Add wardrobe items to reuse them'}</span></div><b>{wardrobeItem ? '$0' : '—'}</b></div><div className="save-line"><span>Unique purchases avoided</span><strong>{uniqueWardrobeItems}</strong></div>{memoryScope ? <div className="memory-confirmed">✓ {memoryScope === 'remembered' ? 'Remembered until you remove it' : 'Temporary for this experience · expires in 30 days'}</div> : <div className="memory-controls"><span>{wardrobeItem ? 'How should Aura use this item?' : 'No wardrobe item selected'}</span><div>{wardrobeItem && <><button onClick={() => setMemoryScope('temporary')}>Use temporarily</button><button onClick={() => setMemoryScope('remembered')}>Remember in my wardrobe</button></>}</div><small>{wardrobeItem ? 'Temporary expires automatically. Remembered stays until you remove it.' : ''}</small></div>}<button className="text-btn">Manage wardrobe →</button></div></div>
      </section>
      <section className="looks"><div className="looks-head"><div><span className="kicker">YOUR EDIT</span><h2>{request.outfits || session.outfits.length} looks, one easy trip</h2><p>Ranked for your style, plans, and budget. <button className="text-btn">Why these?</button></p></div><div className="total-card"><span>PLANNED SPEND</span><strong>${session.newPurchaseCost} <small>/ ${request.totalBudget || 0}</small></strong><div className="progress"><i style={{ width: `${request.totalBudget ? Math.min(session.newPurchaseCost / request.totalBudget * 100, 100) : 0}%` }} /></div><em>${remainingBudget} remaining budget</em></div></div><div className="day-tabs"><button className={activeDay === 'all' ? 'selected' : ''} onClick={() => setActiveDay('all')}>All looks <span>{session.outfits.length}</span></button>{session.outfits.map(outfit => <button className={activeDay === String(outfit.day) ? 'selected' : ''} key={outfit.day} onClick={() => setActiveDay(String(outfit.day))}>Day {outfit.day}</button>)}</div><div className="outfit-list">{visibleOutfits.map(outfit => <article className="outfit-card" key={outfit.id}><div className="outfit-top"><div className="day-badge">DAY {outfit.day}</div><div><h3>{outfit.title}</h3><p>{outfit.setting}</p></div><Score outfit={outfit} /><button className="save">♡</button></div><div className="product-grid">{outfit.products.map(product => <ProductCard product={product} key={product.id} />)}</div><div className="outfit-footer"><p><span>WHY THIS WORKS</span>{outfit.whyItWorks}</p><div className="outfit-cost"><span>NEW SPEND</span><strong>${outfit.newSpend}</strong></div><button className="detail-btn">See details →</button></div></article>)}</div><div className="more-looks"><span>{visibleOutfits.length < session.outfits.length ? `${session.outfits.length - visibleOutfits.length} more looks ready` : 'All looks ready'}</span><button onClick={() => setActiveDay('all')}>Show full trip <span>↓</span></button></div></section>
      <section className="modification-bar"><div><span className="eyebrow">KEEP EXPLORING</span><strong>Want to change something?</strong><p>Aura will replan only the pieces affected by your note.</p></div><div className="modification-input"><input value={modification} onChange={e => setModification(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') applyModification() }} placeholder="Try: Make outfit three more elegant" /><button onClick={applyModification}>Update plan <span>→</span></button></div></section>
      <footer className="checkout-bar"><div><span className="eyebrow">SMART PURCHASE PLAN</span><strong>{totalPieces} pieces <small>· {reusedPieces} reused from your wardrobe</small></strong></div><div className="checkout-total"><span>New purchase cost</span><strong>${session.newPurchaseCost}</strong></div><button className="checkout-btn" onClick={() => setCheckoutOpen(true)}>Review purchase plan <span>→</span></button></footer>
      {checkoutOpen && <div className="modal-backdrop" onClick={() => setCheckoutOpen(false)}><div className="checkout-modal" onClick={e => e.stopPropagation()}><button className="modal-close" onClick={() => setCheckoutOpen(false)}>×</button><span className="kicker">SMART PURCHASE PLAN</span><h2>{tripLabel}</h2><p className="modal-subtitle">Aura found the pieces worth buying and made reuse visible. No payment details are collected.</p><div className="checkout-summary"><div><span>OUTFITS</span><strong>{session.outfits.length}</strong></div><div><span>TOTAL PIECES</span><strong>{totalPieces}</strong></div><div><span>REUSED</span><strong>{reusedPieces}</strong></div><div><span>TO BUY</span><strong>{purchaseItems.length}</strong></div></div><div className="budget-summary"><span>Budget ${request.totalBudget || 0}</span><strong>Planned spend ${session.newPurchaseCost} · ${remainingBudget} remaining</strong></div><div className="selected-list">{purchaseItems.map(product => <div className="selected-row" key={product.id}><div className="mini-product" style={{ backgroundImage: `url(${product.image})` }} /><div><strong>{product.name}</strong><span>{product.retailer} · ${product.price}</span></div><a className="merchant-link" href={product.link} target="_blank" rel="noreferrer">View at retailer →</a></div>)}</div><div className="privacy-note"><span>♧</span><p><strong>Trust by design.</strong> Aura uses temporary preferences for this experience unless you choose to remember a wardrobe item. It never stores payment-card details.</p></div><button className="back-btn" onClick={() => setCheckoutOpen(false)}>Back to edit</button></div></div>}
    </main>
  </div>
}
export default App
