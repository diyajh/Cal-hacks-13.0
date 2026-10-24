from dataclasses import dataclass
import os
from typing import Optional


@dataclass(frozen=True)
class Settings:
    cartesia_api_key: Optional[str]
    cartesia_version: str
    cartesia_stt_model: str
    cartesia_tts_model: str
    cartesia_voice_id: str
    agents_base_url: str
    allowed_origins: tuple[str, ...]


def load_settings() -> Settings:
    origins = tuple(
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    )
    return Settings(
        cartesia_api_key=os.getenv("CARTESIA_API_KEY") or None,
        cartesia_version=os.getenv("CARTESIA_VERSION", "2025-04-16"),
        cartesia_stt_model=os.getenv("CARTESIA_STT_MODEL", "ink-whisper"),
        cartesia_tts_model=os.getenv("CARTESIA_TTS_MODEL", "sonic-2"),
        cartesia_voice_id=os.getenv(
            "CARTESIA_VOICE_ID", "e07c00bc-4134-4eae-9ea4-1a55fb45746b"
        ),
        agents_base_url=os.getenv("AGENTS_BASE_URL", "http://localhost:8001").rstrip("/"),
        allowed_origins=origins,
    )

