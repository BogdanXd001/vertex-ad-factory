import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

from vertex_ad_factory.config import Settings
from vertex_ad_factory.orchestrator import Orchestrator
from vertex_ad_factory.runner import (
    ModelBatch,
    PipelineRunner,
    plan_first_frame_batches,
    summarize_batch,
)
from vertex_ad_factory.services.blueprints import load_blueprint
from vertex_ad_factory.services.runtime_config import RuntimeConfig
from vertex_ad_factory.stages.first_frames import FirstFrameResult
from vertex_ad_factory.stages.voiceover import VoiceoverResult


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_PATH = ROOT / "blueprints" / "oceaura_expert_podcast_30s.json"


class BatchPlanningTests(TestCase):
    def test_blueprint_scenes_are_grouped_by_warm_model_family(self) -> None:
        blueprint = load_blueprint(BLUEPRINT_PATH)
        scenes = [
            {"position": scene.position, "kind": scene.kind.value}
            for scene in blueprint.scenes
        ]

        batches = plan_first_frame_batches(scenes)

        self.assertEqual(
            batches,
            (
                ModelBatch("flux_pulid", (1, 4)),
                ModelBatch("flux_base", (2, 3, 5, 6, 7)),
            ),
        )

    def test_cold_to_warm_speedup_is_reported(self) -> None:
        results = [
            FirstFrameResult(
                job_id="job",
                scene_id=f"scene-{position}",
                position=position,
                prompt_id=f"prompt-{position}",
                seed=position,
                elapsed_seconds=elapsed,
                outputs=[],
                model_family="video_model",
            )
            for position, elapsed in ((1, 600.0), (2, 150.0), (3, 150.0))
        ]

        summary = summarize_batch(ModelBatch("video_model", (1, 2, 3)), results)

        self.assertEqual(summary["cold_seconds"], 600.0)
        self.assertEqual(summary["warm_median_seconds"], 150.0)
        self.assertEqual(summary["cold_to_warm_speedup"], 4.0)


class FakeVoiceover:
    async def execute(self, job_id: str, force: bool = False) -> VoiceoverResult:
        return VoiceoverResult(
            job_id=job_id,
            master_audio_path="master.mp3",
            alignment_path="alignment.json",
            scene_count=7,
            elapsed_seconds=1.0,
            cached=False,
        )


class FakeFirstFrames:
    def __init__(self) -> None:
        self.positions = []

    async def execute(
        self,
        job_id: str,
        position: int,
        reference_image: str,
        seed: int | None = None,
        width: int = 720,
        height: int = 1280,
        force: bool = False,
    ) -> FirstFrameResult:
        self.positions.append(position)
        family = "flux_pulid" if position in {1, 4} else "flux_base"
        return FirstFrameResult(
            job_id=job_id,
            scene_id=f"scene-{position}",
            position=position,
            prompt_id=f"prompt-{position}",
            seed=seed or 0,
            elapsed_seconds=10.0 if len(self.positions) in {1, 3} else 2.0,
            outputs=[{"filename": f"scene-{position}.png"}],
            model_family=family,
        )


class PipelineRunnerTests(IsolatedAsyncioTestCase):
    async def test_runner_uses_model_batches_and_stops_at_missing_i2v(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(
                project_root=root,
                database_path=root / "data" / "test.sqlite3",
                workflows_dir=root / "workflows",
                runs_dir=root / "runs",
                runtime_config_path=root / "data" / "runtime.json",
            )
            orchestrator = Orchestrator(settings)
            job = orchestrator.create_from_blueprint(load_blueprint(BLUEPRINT_PATH))
            fake_frames = FakeFirstFrames()
            runner = PipelineRunner(
                settings,
                orchestrator.database,
                RuntimeConfig("secret", "voice"),
                voiceover=FakeVoiceover(),
                first_frames=fake_frames,
            )

            result = await runner.execute(
                job.job_id,
                reference_image="reference.png",
                base_seed=42,
            )

            self.assertEqual(fake_frames.positions, [1, 4, 2, 3, 5, 6, 7])
            self.assertEqual(result.status, "waiting_input")
            stored = orchestrator.database.get_job(job.job_id)
            self.assertEqual(stored["current_stage"], "image_to_video")
            performance = json.loads(Path(result.performance_path).read_text())
            self.assertFalse(performance["model_unload_requested"])
            self.assertEqual(
                [batch["model_family"] for batch in performance["batches"]],
                ["flux_pulid", "flux_base"],
            )
