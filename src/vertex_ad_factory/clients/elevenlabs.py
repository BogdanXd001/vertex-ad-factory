from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp


class ElevenLabsError(RuntimeError):
    """Raised when ElevenLabs rejects a text-to-speech request."""


@dataclass(frozen=True, slots=True)
class TimedSpeech:
    audio: bytes
    alignment: dict[str, Any]
    normalized_alignment: dict[str, Any] | None


class ElevenLabsClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.elevenlabs.io",
        timeout_seconds: int = 300,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ElevenLabs API key is required")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None
        self._aiohttp: Any = None

    async def __aenter__(self) -> ElevenLabsClient:
        try:
            import aiohttp
        except ImportError as error:
            raise RuntimeError(
                "aiohttp is required for ElevenLabs requests; install the project "
                "with its dependencies"
            ) from error
        self._aiohttp = aiohttp
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("Use ElevenLabsClient with 'async with'")
        return self._session

    async def create_speech_with_timing(
        self,
        text: str,
        voice_id: str,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
    ) -> TimedSpeech:
        if not text.strip():
            raise ValueError("voiceover text cannot be empty")
        if not voice_id.strip():
            raise ValueError("ElevenLabs voice ID is required")
        url = f"{self.base_url}/v1/text-to-speech/{voice_id.strip()}/with-timestamps"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        params = {"output_format": output_format}
        payload = {"text": text, "model_id": model_id}
        async with self.session.post(
            url,
            headers=headers,
            params=params,
            json=payload,
        ) as response:
            try:
                body = await response.json()
            except (self._aiohttp.ContentTypeError, ValueError) as error:
                raw = await response.text()
                raise ElevenLabsError(
                    f"Invalid response from ElevenLabs ({response.status}): {raw[:500]}"
                ) from error
            if response.status >= 400:
                detail = body.get("detail", body) if isinstance(body, dict) else body
                raise ElevenLabsError(
                    f"ElevenLabs {response.status}: {str(detail)[:1000]}"
                )
        if not isinstance(body, dict) or not body.get("audio_base64"):
            raise ElevenLabsError("ElevenLabs response did not contain audio_base64")
        alignment = body.get("alignment")
        if not isinstance(alignment, dict):
            raise ElevenLabsError("ElevenLabs response did not contain alignment")
        try:
            audio = base64.b64decode(body["audio_base64"], validate=True)
        except (ValueError, TypeError) as error:
            raise ElevenLabsError("ElevenLabs returned invalid base64 audio") from error
        normalized = body.get("normalized_alignment")
        return TimedSpeech(
            audio=audio,
            alignment=alignment,
            normalized_alignment=normalized if isinstance(normalized, dict) else None,
        )
