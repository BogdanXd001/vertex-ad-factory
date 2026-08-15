from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from vertex_ad_factory.database import Database
from vertex_ad_factory.models import AdJob, JobStatus, Scene, SceneKind, Stage


class DatabaseTests(TestCase):
    def test_job_and_scene_are_persisted(self) -> None:
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            database.initialize()

            job = database.create_job(
                AdJob(product_name="Test Product", angle="Test Angle")
            )
            database.add_scene(
                Scene(
                    job_id=job.job_id,
                    position=1,
                    kind=SceneKind.A_ROLL,
                    duration_seconds=6,
                    narration="Test narration",
                )
            )
            scene = database.get_scene_by_position(job.job_id, 1)
            self.assertIsNotNone(scene)
            database.record_scene_output(
                scene["scene_id"],
                "first_frame",
                {"prompt_id": "prompt-1", "outputs": [{"filename": "frame.png"}]},
            )
            stage_run_id = database.start_stage_run(job.job_id, Stage.FIRST_FRAMES)
            database.finish_stage_run(stage_run_id, {"elapsed_seconds": 1.5})
            database.update_job_status(
                job.job_id, JobStatus.PLANNED, current_stage="planning"
            )

            stored = database.get_job(job.job_id)
            self.assertIsNotNone(stored)
            self.assertEqual(stored["status"], "planned")
            self.assertTrue(database.all_scenes_have_output(job.job_id, "first_frame"))
