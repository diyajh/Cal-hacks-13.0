from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4

from .config import load_settings
from .agents_client import AgentsClient, AgentsUnavailableError
from .schemas import TranscriptionResponse, VoiceTurnRequest, VoiceTurnResponse
from .session_mapper import to_style_session
from .voice import CartesiaVoiceGateway, ProviderNotConfiguredError


settings = load_settings()
SESSION_CACHE: dict[str, dict[str, object]] = {}
app = FastAPI(title="Aura Voice API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "cartesia_configured": bool(settings.cartesia_api_key),
        "stt_model": settings.cartesia_stt_model,
        "tts_model": settings.cartesia_tts_model,
        "agents_base_url": settings.agents_base_url,
    }


@app.post("/api/style-sessions")
async def create_style_session(request: dict[str, object]) -> dict[str, object]:
    prompt = str(request.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt is required")
    try:
        result = await AgentsClient(settings).plan(prompt, "demo_user", f"session_{uuid4().hex[:10]}")
    except AgentsUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    session = to_style_session(result)
    SESSION_CACHE[str(session["session"])] = session
    return session


@app.get("/api/style-sessions/{session_id}")
async def get_style_session(session_id: str) -> dict[str, object]:
    session = SESSION_CACHE.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="style session not found")
    return session


@app.post("/api/style-sessions/{session_id}/modifications")
async def modify_style_session(session_id: str, request: dict[str, object]) -> dict[str, object]:
    instruction = str(request.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(status_code=422, detail="instruction is required")
    try:
        result = await AgentsClient(settings).modify(session_id, "demo_user", instruction)
    except AgentsUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    session = to_style_session(result)
    SESSION_CACHE[session_id] = session
    return session


@app.post("/api/voice-sessions/{session_id}/turns", response_model=VoiceTurnResponse)
async def voice_turn(session_id: str, request: VoiceTurnRequest) -> VoiceTurnResponse:
    if request.session_id != session_id:
        raise HTTPException(status_code=400, detail="session_id does not match route")

    gateway = CartesiaVoiceGateway(settings)
    try:
        plan = await AgentsClient(settings).plan(
            request.transcript, "demo_user", session_id
        )
        recommendation = plan.get("final_recommendation") or {}
        response_text = recommendation.get("message") or (
            f"I found {len(recommendation.get('outfits') or [])} looks that match your request."
        )
        speech = await gateway.synthesize(str(response_text))
        agent_events = recommendation.get("agent_events") or []
    except ProviderNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except AgentsUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NotImplementedError as error:
        raise HTTPException(status_code=501, detail=str(error)) from error

    return VoiceTurnResponse(
        session_id=session_id,
        transcript=request.transcript,
        response_text=str(response_text),
        audio_data_url=speech.audio_data_url,
        provider="cartesia",
        status="completed",
        agent_events=agent_events,
    )


@app.post("/api/voice-sessions/{session_id}/transcribe", response_model=TranscriptionResponse)
async def transcribe_voice(session_id: str, audio: UploadFile = File(...)) -> TranscriptionResponse:
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=415, detail="an audio upload is required")
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=422, detail="audio upload is empty")
    try:
        result = await CartesiaVoiceGateway(settings).transcribe(
            audio.filename or "voice.webm", data, audio.content_type
        )
    except ProviderNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return TranscriptionResponse(
        session_id=session_id,
        transcript=result.text,
        provider="cartesia",
        model=result.model,
    )

