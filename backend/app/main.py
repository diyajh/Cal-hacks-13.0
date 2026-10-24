from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import load_settings
from .agents_client import AgentsClient, AgentsUnavailableError
from .schemas import AgentEvent, TranscriptionResponse, VoiceTurnRequest, VoiceTurnResponse
from .session_mapper import to_style_session
from .voice import CartesiaVoiceGateway, ProviderNotConfiguredError


settings = load_settings()
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
        result = await AgentsClient(settings).plan(prompt, "demo_user", "session_live")
    except AgentsUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return to_style_session(result)


@app.post("/api/style-sessions/{session_id}/modifications")
async def modify_style_session(session_id: str, request: dict[str, object]) -> dict[str, object]:
    instruction = str(request.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(status_code=422, detail="instruction is required")
    try:
        result = await AgentsClient(settings).modify(session_id, "demo_user", instruction)
    except AgentsUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return to_style_session(result)


@app.post("/api/voice-sessions/{session_id}/turns", response_model=VoiceTurnResponse)
async def voice_turn(session_id: str, request: VoiceTurnRequest) -> VoiceTurnResponse:
    if request.session_id != session_id:
        raise HTTPException(status_code=400, detail="session_id does not match route")

    gateway = CartesiaVoiceGateway(settings)
    try:
        speech = await gateway.synthesize(request.transcript)
    except ProviderNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NotImplementedError as error:
        raise HTTPException(status_code=501, detail=str(error)) from error

    return VoiceTurnResponse(
        session_id=session_id,
        transcript=request.transcript,
        response_text="Voice turn accepted.",
        audio_data_url=speech.audio_data_url,
        provider="cartesia",
        status="completed",
        agent_events=[
            AgentEvent(
                agent="style",
                status="started",
                message="Voice request accepted by the style session",
            )
        ],
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

