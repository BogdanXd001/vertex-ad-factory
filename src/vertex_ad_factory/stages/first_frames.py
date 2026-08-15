from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic

from ..clients.comfy import ComfyClient
from ..config import Settings
from ..database import Database
from ..models import JobStatus, Stage
from ..services.workflows import (
    FirstFrameBindings,
    bind_first_frame,
    load_api_workflow,
    save_api_workflow,
)


@dataclass(frozen=True, slots=True)
class FirstFrameResult:
    job_id: str
    scene_id: str
    position: int
    prompt_id: str
    seed: int
    elapsed_seconds: float
    outputs: list[dict]
    cached: bool = False


class FirstFrameStage:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    async def execute(
        self,
        job_id: str,
        position: int,
        reference_image: str,
        seed: int | None = None,
        width: int = 832,
        height: int = 1216,
        force: bool = False,
    ) -> FirstFrameResult:
        job = self.database.get_job(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        scene = self.database.get_scene_by_position(job_id, position)
        if scene is None:
            raise KeyError(f"Unknown scene position {position} for job {job_id}")
        if scene["kind"] != "a_roll":
            raise ValueError("PuLID presenter first frames require an A-roll scene")

        previous = scene["output"].get("first_frame")
        if previous and not force:
            return FirstFrameResult(
                job_id=job_id,
                scene_id=scene["scene_id"],
                position=position,
                prompt_id=previous["prompt_id"],
                seed=int(previous["seed"]),
                elapsed_seconds=float(previous["elapsed_seconds"]),
                outputs=list(previous["outputs"]),
                cached=True,
            )

        output_prefix = (
            f"vertex_ad_factory/{job_id}/scene_{position:02d}/first_frame"
        )
        template = load_api_workflow(
            self.settings.workflows_dir / "aroll_first_frame.api.json"
        )
        workflow, resolved_seed = bind_first_frame(
            template,
            FirstFrameBindings(
                prompt=scene["visual_prompt"],
                reference_image=reference_image,
                output_prefix=output_prefix,
                width=width,
                height=height,
                seed=seed,
            ),
        )
        payload_path = (
            self.settings.runs_dir
            / job_id
            / f"scene_{position:02d}"
            / "first_frame.api.json"
        )
        save_api_workflow(workflow, payload_path)

        stage_run_id = self.database.start_stage_run(job_id, Stage.FIRST_FRAMES)
        started = monotonic()
        try:
            async with ComfyClient(self.settings.comfy_url) as client:
                prompt_id = await client.queue_prompt(workflow)
                history = await client.wait_for_completion(prompt_id)
                outputs = [
                    asdict(output) for output in client.outputs_from_history(history)
                ]
            if not outputs:
                raise RuntimeError("ComfyUI completed without image outputs")

            elapsed = round(monotonic() - started, 3)
            output = {
                "prompt_id": prompt_id,
                "seed": resolved_seed,
                "elapsed_seconds": elapsed,
                "payload_path": str(payload_path),
                "outputs": outputs,
            }
            self.database.record_scene_output(
                scene["scene_id"], "first_frame", output
            )
            self.database.finish_stage_run(
                stage_run_id,
                {
                    "scene_id": scene["scene_id"],
                    "position": position,
                    "prompt_id": prompt_id,
                    "seed": resolved_seed,
                    "elapsed_seconds": elapsed,
                },
            )
            if self.database.all_scenes_have_output(job_id, "first_frame"):
                self.database.update_job_status(
                    job_id, JobStatus.FRAMES_READY, Stage.FIRST_FRAMES.value
                )
            return FirstFrameResult(
                job_id=job_id,
                scene_id=scene["scene_id"],
                position=position,
                prompt_id=prompt_id,
                seed=resolved_seed,
                elapsed_seconds=elapsed,
                outputs=outputs,
            )
        except Exception as error:
            self.database.fail_stage_run(stage_run_id, str(error))
            self.database.update_job_status(
                job_id, JobStatus.FAILED, Stage.FIRST_FRAMES.value, str(error)
            )
            raise
