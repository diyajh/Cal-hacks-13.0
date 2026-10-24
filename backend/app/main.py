from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import load_settings
from .schemas import AgentEvent, VoiceTurnRequest, VoiceTurnResponse
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
    }


@app.post("/api/voice-sessions/{session_id}/turns", response_model=VoiceTurnResponse)
async def voice_turn(session_id: str, request: VoiceTurnRequest) -> VoiceTurnResponse:
    if request.session_id != session_id:
        raise HTTPException(status_code=400, detail="session_id does not match route")

    gateway = CartesiaVoiceGateway(settings)
    try:
        await gateway.transcribe_and_speak(request.transcript)
    except ProviderNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NotImplementedError as error:
        raise HTTPException(status_code=501, detail=str(error)) from error

    return VoiceTurnResponse(
        session_id=session_id,
        transcript=request.transcript,
        response_text="Voice turn accepted.",
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

