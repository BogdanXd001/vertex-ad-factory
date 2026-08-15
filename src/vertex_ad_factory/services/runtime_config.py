from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "mp3_44100_128"

    @property
    def voiceover_ready(self) -> bool:
        return bool(
            self.elevenlabs_api_key.strip() and self.elevenlabs_voice_id.strip()
        )

    def public_dict(self) -> dict:
        return {
            "voiceover_ready": self.voiceover_ready,
            "elevenlabs_voice_id": self.elevenlabs_voice_id,
            "elevenlabs_model_id": self.elevenlabs_model_id,
            "elevenlabs_output_format": self.elevenlabs_output_format,
        }


class RuntimeConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> RuntimeConfig:
        if not self.path.exists():
            return RuntimeConfig(
                elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
                elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", ""),
                elevenlabs_model_id=os.getenv(
                    "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
                ),
                elevenlabs_output_format=os.getenv(
                    "ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"
                ),
            )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("runtime config must be a JSON object")
        return RuntimeConfig(
            elevenlabs_api_key=str(payload.get("elevenlabs_api_key", "")),
            elevenlabs_voice_id=str(payload.get("elevenlabs_voice_id", "")),
            elevenlabs_model_id=str(
                payload.get("elevenlabs_model_id", "eleven_multilingual_v2")
            ),
            elevenlabs_output_format=str(
                payload.get("elevenlabs_output_format", "mp3_44100_128")
            ),
        )

    def update_voiceover(
        self,
        api_key: str | None,
        voice_id: str,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
    ) -> RuntimeConfig:
        previous = self.load()
        resolved_key = previous.elevenlabs_api_key if api_key is None else api_key.strip()
        config = RuntimeConfig(
            elevenlabs_api_key=resolved_key,
            elevenlabs_voice_id=voice_id.strip(),
            elevenlabs_model_id=model_id.strip(),
            elevenlabs_output_format=output_format.strip(),
        )
        if not config.elevenlabs_model_id or not config.elevenlabs_output_format:
            raise ValueError("ElevenLabs model and output format cannot be empty")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(self.path)
        self.path.chmod(0o600)
        return config

