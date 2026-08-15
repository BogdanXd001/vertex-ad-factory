from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .config import Settings
from .database import Database
from .models import JobStatus, Stage
from .services.runtime_config import RuntimeConfig
from .stages.first_frames import FirstFrameResult, FirstFrameStage
from .stages.voiceover import VoiceoverResult, VoiceoverStage


@dataclass(frozen=True, slots=True)
class ModelBatch:
    model_family: str
    positions: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PipelineResult:
    job_id: str
    status: str
    voiceover: dict
    first_frames: tuple[dict, ...]
    performance_path: str
    next_required_input: str


class VoiceoverExecutor(Protocol):
    async def execute(self, job_id: str, force: bool = False) -> VoiceoverResult: ...


class FirstFrameExecutor(Protocol):
    async def execute(
        self,
        job_id: str,
        position: int,
        reference_image: str,
        seed: int | None = None,
        width: int = 720,
        height: int = 1280,
        force: bool = False,
    ) -> FirstFrameResult: ...


def plan_first_frame_batches(scenes: list[dict]) -> tuple[ModelBatch, ...]:
    """Group consecutive work by model family to avoid cold model reloads."""
    a_roll = tuple(
        int(scene["position"]) for scene in scenes if scene["kind"] == "a_roll"
    )
    b_roll = tuple(
        int(scene["position"]) for scene in scenes if scene["kind"] == "b_roll"
    )
    batches = []
    if a_roll:
        batches.append(ModelBatch("flux_pulid", a_roll))
    if b_roll:
        batches.append(ModelBatch("flux_base", b_roll))
    return tuple(batches)


def summarize_batch(
    batch: ModelBatch,
    results: list[FirstFrameResult],
) -> dict:
    generated = [result for result in results if not result.cached]
    warm_seconds = [result.elapsed_seconds for result in generated[1:]]
    cold_seconds = generated[0].elapsed_seconds if generated else None
    warm_median = statistics.median(warm_seconds) if warm_seconds else None
    speedup = (
        round(cold_seconds / warm_median, 2)
        if cold_seconds and warm_median and warm_median > 0
        else None
    )
    return {
        "model_family": batch.model_family,
        "positions": list(batch.positions),
        "generated_count": len(generated),
        "cached_count": len(results) - len(generated),
        "cold_seconds": cold_seconds,
        "warm_median_seconds": warm_median,
        "cold_to_warm_speedup": speedup,
        "scenes": [
            {
                "position": result.position,
                "elapsed_seconds": result.elapsed_seconds,
                "cached": result.cached,
            }
            for result in results
        ],
    }


class PipelineRunner:
    """Run every currently configured stage without unloading ComfyUI models."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        runtime: RuntimeConfig,
        voiceover: VoiceoverExecutor | None = None,
        first_frames: FirstFrameExecutor | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.runtime = runtime
        self.voiceover = voiceover or VoiceoverStage(settings, database, runtime)
        self.first_frames = first_frames or FirstFrameStage(settings, database)

    async def execute(
        self,
        job_id: str,
        reference_image: str,
        base_seed: int = 42,
        width: int = 720,
        height: int = 1280,
        force: bool = False,
    ) -> PipelineResult:
        if self.database.get_job(job_id) is None:
            raise KeyError(f"Unknown job: {job_id}")
        if not self.runtime.voiceover_ready:
            raise ValueError("Configure the ElevenLabs API key and voice ID first")

        self.database.update_job_status(
            job_id, JobStatus.RUNNING, Stage.VOICEOVER.value
        )
        try:
            voice_result = await self.voiceover.execute(job_id, force=force)
            scenes = self.database.list_scenes(job_id)
            batches = plan_first_frame_batches(scenes)
            frame_payloads: list[dict] = []
            performance_batches: list[dict] = []
            performance_path = (
                self.settings.runs_dir / job_id / "performance.json"
            )

            self.database.update_job_status(
                job_id, JobStatus.RUNNING, Stage.FIRST_FRAMES.value
            )
            for batch in batches:
                batch_results: list[FirstFrameResult] = []
                for position in batch.positions:
                    result = await self.first_frames.execute(
                        job_id=job_id,
                        position=position,
                        reference_image=reference_image,
                        seed=base_seed + position - 1,
                        width=width,
                        height=height,
                        force=force,
                    )
                    batch_results.append(result)
                    frame_payloads.append(asdict(result))
                    self._write_performance(
                        performance_path,
                        job_id,
                        performance_batches
                        + [summarize_batch(batch, batch_results)],
                    )
                performance_batches.append(summarize_batch(batch, batch_results))

            self._write_performance(
                performance_path,
                job_id,
                performance_batches,
            )
            next_input = (
                "Export the working image-to-video ComfyUI workflow in API format "
                "to enable video, lip-sync and assembly stages."
            )
            self.database.update_job_status(
                job_id, JobStatus.WAITING_INPUT, Stage.IMAGE_TO_VIDEO.value
            )
            return PipelineResult(
                job_id=job_id,
                status=JobStatus.WAITING_INPUT.value,
                voiceover=asdict(voice_result),
                first_frames=tuple(frame_payloads),
                performance_path=str(performance_path),
                next_required_input=next_input,
            )
        except Exception as error:
            self.database.update_job_status(
                job_id,
                JobStatus.FAILED,
                self.database.get_job(job_id)["current_stage"],
                str(error),
            )
            raise

    @staticmethod
    def _write_performance(path: Path, job_id: str, batches: list[dict]) -> None:
        PipelineRunner._write_json(
            path,
            {
                "job_id": job_id,
                "strategy": "model_family_batches",
                "model_unload_requested": False,
                "batches": batches,
            },
        )

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
