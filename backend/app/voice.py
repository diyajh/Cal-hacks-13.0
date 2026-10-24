from dataclasses import dataclass

from .config import Settings


class ProviderNotConfiguredError(RuntimeError):
    """Raised when the server has no Cartesia credential configured."""


@dataclass(frozen=True)
class CartesiaVoiceGateway:
    settings: Settings

    def assert_configured(self) -> None:
        if not self.settings.cartesia_api_key:
            raise ProviderNotConfiguredError(
                "CARTESIA_API_KEY is not configured on the backend"
            )

    async def transcribe_and_speak(self, transcript: str) -> None:
        """Provider boundary for Ink STT and Sonic TTS.

        The request/response contract is intentionally isolated here. The next
        slice will replace this method with the Cartesia SDK/WebSocket calls;
        routes and frontend contracts should not need to change.
        """
        self.assert_configured()
        raise NotImplementedError("Cartesia transport is the next implementation slice")

