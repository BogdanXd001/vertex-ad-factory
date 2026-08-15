from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .config import Settings
from .database import Database
from .models import JobStatus, Stage
from .orchestrator import Orchestrator
from .runner import PipelineRunner
from .services.blueprints import load_blueprint
from .services.runtime_config import RuntimeConfigStore


@dataclass(frozen=True, slots=True)
class StartRequest:
    blueprint: str
    reference_image: str = "A1_contradiction.png"
    seed: int = 42
    width: int = 720
    height: int = 1280


class PipelineManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_directories()
        self.database = Database(settings.database_path)
        self.database.initialize()
        self.runtime_store = RuntimeConfigStore(settings.runtime_config_path)
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def available_blueprints(self) -> list[dict]:
        blueprint_dir = self.settings.project_root / "blueprints"
        results = []
        for path in sorted(blueprint_dir.glob("*.json")):
            blueprint = load_blueprint(path)
            results.append({"file": path.name, **blueprint.summary()})
        return results

    def status(self) -> dict:
        jobs = []
        for job in self.database.list_jobs(limit=30):
            scenes = self.database.list_scenes(job["job_id"])
            jobs.append(
                {
                    "job_id": job["job_id"],
                    "product_name": job["product_name"],
                    "status": job["status"],
                    "current_stage": job["current_stage"],
                    "error": job["error"],
                    "created_at": job["created_at"],
                    "scenes_total": len(scenes),
                    "voice_scenes_ready": sum(
                        "voiceover" in scene["output"] for scene in scenes
                    ),
                    "frames_ready": sum(
                        "first_frame" in scene["output"] for scene in scenes
                    ),
                    "running_in_background": job["job_id"] in self._tasks,
                }
            )
        return {
            "runtime": self.runtime_store.load().public_dict(),
            "jobs": jobs,
            "blueprints": self.available_blueprints(),
            "automated_through": Stage.FIRST_FRAMES.value,
            "next_required_input": "image_to_video_api_workflow",
        }

    def start(self, request: StartRequest) -> dict:
        runtime = self.runtime_store.load()
        if not runtime.voiceover_ready:
            raise ValueError("Save the ElevenLabs API key and voice ID first")
        blueprint_path = self._blueprint_path(request.blueprint)
        self._validate_reference_image(request.reference_image)
        if request.width < 64 or request.height < 64:
            raise ValueError("width and height must be at least 64 pixels")

        blueprint = load_blueprint(blueprint_path)
        job = Orchestrator(self.settings).create_from_blueprint(blueprint)
        self._schedule(job.job_id, request)
        return {
            "job_id": job.job_id,
            "status": JobStatus.QUEUED.value,
            "scene_count": len(blueprint.scenes),
        }

    def resume(self, job_id: str, request: StartRequest) -> dict:
        if self.database.get_job(job_id) is None:
            raise KeyError(f"Unknown job: {job_id}")
        if job_id in self._tasks:
            raise ValueError(f"Job is already running: {job_id}")
        if not self.runtime_store.load().voiceover_ready:
            raise ValueError("Save the ElevenLabs API key and voice ID first")
        self._validate_reference_image(request.reference_image)
        self._schedule(job_id, request)
        return {"job_id": job_id, "status": JobStatus.QUEUED.value}

    def _schedule(self, job_id: str, request: StartRequest) -> None:
        self.database.update_job_status(
            job_id, JobStatus.QUEUED, Stage.VOICEOVER.value
        )
        task = asyncio.create_task(
            self._run(
                job_id,
                request.reference_image,
                request.seed,
                request.width,
                request.height,
            ),
            name=f"vertex-ad-factory-{job_id}",
        )
        self._tasks[job_id] = task
        task.add_done_callback(
            lambda finished, scheduled_id=job_id: self._task_done(
                scheduled_id, finished
            )
        )

    async def _run(
        self,
        job_id: str,
        reference_image: str,
        seed: int,
        width: int,
        height: int,
    ) -> None:
        runtime = self.runtime_store.load()
        runner = PipelineRunner(self.settings, self.database, runtime)
        await runner.execute(
            job_id,
            reference_image=reference_image,
            base_seed=seed,
            width=width,
            height=height,
        )

    def _task_done(self, job_id: str, task: asyncio.Task[Any]) -> None:
        self._tasks.pop(job_id, None)
        if not task.cancelled():
            task.exception()

    def _blueprint_path(self, name: str) -> Path:
        if Path(name).name != name or not name.endswith(".json"):
            raise ValueError("Invalid blueprint name")
        path = self.settings.project_root / "blueprints" / name
        if not path.is_file():
            raise FileNotFoundError(f"Unknown blueprint: {name}")
        return path

    @staticmethod
    def _validate_reference_image(value: str) -> None:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not value.strip():
            raise ValueError("reference_image must be a safe ComfyUI input path")
