from dataclasses import dataclass
import base64

from .config import Settings


class ProviderNotConfiguredError(RuntimeError):
    """Raised when the server has no Cartesia credential configured."""


@dataclass(frozen=True)
class SynthesizedSpeech:
    audio_data_url: str
    content_type: str


@dataclass(frozen=True)
class Transcription:
    text: str
    model: str


@dataclass(frozen=True)
class CartesiaVoiceGateway:
    settings: Settings

    def assert_configured(self) -> None:
        if not self.settings.cartesia_api_key:
            raise ProviderNotConfiguredError(
                "CARTESIA_API_KEY is not configured on the backend"
            )

    async def synthesize(self, transcript: str) -> SynthesizedSpeech:
        """Generate browser-playable audio through Cartesia Sonic.

        The API key and SDK client remain entirely inside the backend. Returning
        a data URL is suitable for the first local slice; the streaming version
        can later replace it with an audio stream without changing the provider
        boundary.
        """
        self.assert_configured()
        from cartesia import AsyncCartesia

        async with AsyncCartesia(api_key=self.settings.cartesia_api_key) as client:
            response = await client.tts.generate(
                model_id=self.settings.cartesia_tts_model,
                transcript=transcript,
                voice=self.settings.cartesia_voice_id,
                language="en",
                output_format={
                    "container": "wav",
                    "encoding": "pcm_f32le",
                    "sample_rate": 44100,
                },
            )
            audio = await response.read()

        encoded = base64.b64encode(audio).decode("ascii")
        return SynthesizedSpeech(
            audio_data_url=f"data:audio/wav;base64,{encoded}",
            content_type="audio/wav",
        )

    async def transcribe(self, filename: str, audio: bytes, content_type: str) -> Transcription:
        """Transcribe one recorded browser audio blob through Cartesia Ink."""
        self.assert_configured()
        from cartesia import AsyncCartesia

        async with AsyncCartesia(api_key=self.settings.cartesia_api_key) as client:
            response = await client.stt.transcribe(
                file=(filename, audio, content_type),
                model=self.settings.cartesia_stt_model,
                language="en",
            )
        return Transcription(text=response.text, model=self.settings.cartesia_stt_model)

