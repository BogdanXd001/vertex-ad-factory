from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from ..clients.elevenlabs import ElevenLabsClient, TimedSpeech
from ..config import Settings
from ..database import Database
from ..models import JobStatus, Stage
from ..services.runtime_config import RuntimeConfig


@dataclass(frozen=True, slots=True)
class ScriptScene:
    scene_id: str
    position: int
    narration: str
    character_start: int
    character_end: int


@dataclass(frozen=True, slots=True)
class SceneTiming:
    scene_id: str
    position: int
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True, slots=True)
class VoiceoverResult:
    job_id: str
    master_audio_path: str
    alignment_path: str
    scene_count: int
    elapsed_seconds: float
    cached: bool


def build_master_script(scenes: list[dict]) -> tuple[str, list[ScriptScene]]:
    if not scenes:
        raise ValueError("voiceover requires at least one scene")
    chunks: list[str] = []
    ranges: list[ScriptScene] = []
    cursor = 0
    for scene in scenes:
        narration = str(scene["narration"]).strip()
        if not narration:
            raise ValueError(f"scene {scene['position']} narration cannot be empty")
        if chunks:
            separator = "\n\n"
            chunks.append(separator)
            cursor += len(separator)
        start = cursor
        chunks.append(narration)
        cursor += len(narration)
        ranges.append(
            ScriptScene(
                scene_id=str(scene["scene_id"]),
                position=int(scene["position"]),
                narration=narration,
                character_start=start,
                character_end=cursor,
            )
        )
    return "".join(chunks), ranges


def scene_timings_from_alignment(
    script_scenes: list[ScriptScene],
    alignment: dict[str, Any],
) -> list[SceneTiming]:
    characters = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends = alignment.get("character_end_times_seconds")
    if not isinstance(characters, list) or not isinstance(starts, list) or not isinstance(
        ends, list
    ):
        raise ValueError("alignment is missing character timing arrays")
    if not characters or not (len(characters) == len(starts) == len(ends)):
        raise ValueError("alignment character timing arrays have inconsistent lengths")
    aligned_text = "".join(str(character) for character in characters)
    timings: list[SceneTiming] = []
    search_from = 0
    for scene in script_scenes:
        start_index = aligned_text.find(scene.narration, search_from)
        if start_index < 0:
            raise ValueError(
                f"could not locate scene {scene.position} narration in alignment"
            )
        end_index = start_index + len(scene.narration) - 1
        timings.append(
            SceneTiming(
                scene_id=scene.scene_id,
                position=scene.position,
                start_seconds=float(starts[start_index]),
                end_seconds=float(ends[end_index]),
            )
        )
        search_from = end_index + 1
    return timings


class VoiceoverStage:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        runtime: RuntimeConfig,
    ) -> None:
        self.settings = settings
        self.database = database
        self.runtime = runtime

    async def execute(self, job_id: str, force: bool = False) -> VoiceoverResult:
        job = self.database.get_job(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        if not self.runtime.voiceover_ready:
            raise ValueError("ElevenLabs API key and voice ID are not configured")
        scenes = self.database.list_scenes(job_id)
        master_text, script_scenes = build_master_script(scenes)
        voice_dir = self.settings.runs_dir / job_id / "voiceover"
        master_path = voice_dir / "master.mp3"
        response_path = voice_dir / "elevenlabs_response.json"
        alignment_path = voice_dir / "alignment.json"
        manifest_path = voice_dir / "manifest.json"
        expected_manifest = {
            "text_sha256": hashlib.sha256(master_text.encode("utf-8")).hexdigest(),
            "voice_id": self.runtime.elevenlabs_voice_id,
            "model_id": self.runtime.elevenlabs_model_id,
            "output_format": self.runtime.elevenlabs_output_format,
        }
        previous_outputs = [scene["output"].get("voiceover") for scene in scenes]
        if (
            not force
            and all(previous_outputs)
            and master_path.exists()
            and alignment_path.exists()
        ):
            return VoiceoverResult(
                job_id=job_id,
                master_audio_path=str(master_path),
                alignment_path=str(alignment_path),
                scene_count=len(scenes),
                elapsed_seconds=0.0,
                cached=True,
            )

        voice_dir.mkdir(parents=True, exist_ok=True)
        stage_run_id = self.database.start_stage_run(job_id, Stage.VOICEOVER)
        started = monotonic()
        try:
            speech: TimedSpeech
            can_reuse_master = False
            if not force and manifest_path.exists() and response_path.exists() and master_path.exists():
                previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                can_reuse_master = previous_manifest == expected_manifest
            if can_reuse_master:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
                speech = TimedSpeech(
                    audio=master_path.read_bytes(),
                    alignment=response_payload["alignment"],
                    normalized_alignment=response_payload.get("normalized_alignment"),
                )
            else:
                async with ElevenLabsClient(
                    self.runtime.elevenlabs_api_key
                ) as client:
                    speech = await client.create_speech_with_timing(
                        master_text,
                        voice_id=self.runtime.elevenlabs_voice_id,
                        model_id=self.runtime.elevenlabs_model_id,
                        output_format=self.runtime.elevenlabs_output_format,
                    )
                master_path.write_bytes(speech.audio)
                response_path.write_text(
                    json.dumps(
                        {
                            "alignment": speech.alignment,
                            "normalized_alignment": speech.normalized_alignment,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifest_path.write_text(
                    json.dumps(expected_manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            try:
                timings = scene_timings_from_alignment(script_scenes, speech.alignment)
            except ValueError:
                if speech.normalized_alignment is None:
                    raise
                timings = scene_timings_from_alignment(
                    script_scenes, speech.normalized_alignment
                )
            if shutil.which("ffmpeg") is None:
                raise RuntimeError("ffmpeg is required to split the master voiceover")
            alignment_payload = {
                "master_text": master_text,
                "segments": [asdict(timing) for timing in timings],
            }
            alignment_path.write_text(
                json.dumps(alignment_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            for timing in timings:
                scene_path = voice_dir / f"scene_{timing.position:02d}.wav"
                if force or not scene_path.exists():
                    await self._split_audio(master_path, scene_path, timing)
                self.database.record_scene_output(
                    timing.scene_id,
                    "voiceover",
                    {
                        "path": str(scene_path),
                        "start_seconds": round(timing.start_seconds, 3),
                        "end_seconds": round(timing.end_seconds, 3),
                        "duration_seconds": round(timing.duration_seconds, 3),
                    },
                )
            elapsed = round(monotonic() - started, 3)
            self.database.finish_stage_run(
                stage_run_id,
                {
                    "scene_count": len(timings),
                    "elapsed_seconds": elapsed,
                    "master_reused": can_reuse_master,
                },
            )
            self.database.update_job_status(
                job_id,
                JobStatus.VOICE_READY,
                Stage.VOICEOVER.value,
            )
            return VoiceoverResult(
                job_id=job_id,
                master_audio_path=str(master_path),
                alignment_path=str(alignment_path),
                scene_count=len(timings),
                elapsed_seconds=elapsed,
                cached=False,
            )
        except Exception as error:
            self.database.fail_stage_run(stage_run_id, str(error))
            self.database.update_job_status(
                job_id,
                JobStatus.FAILED,
                Stage.VOICEOVER.value,
                str(error),
            )
            raise

    @staticmethod
    async def _split_audio(
        master_path: Path,
        destination: Path,
        timing: SceneTiming,
    ) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(master_path),
            "-ss",
            f"{timing.start_seconds:.6f}",
            "-t",
            f"{timing.duration_seconds:.6f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(destination),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed for scene {timing.position}: "
                f"{stderr.decode(errors='replace')[:1000]}"
            )

