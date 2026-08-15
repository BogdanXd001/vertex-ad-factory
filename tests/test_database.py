from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from vertex_ad_factory.database import Database
from vertex_ad_factory.models import AdJob, JobStatus, Scene, SceneKind


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
            database.update_job_status(
                job.job_id, JobStatus.PLANNED, current_stage="planning"
            )

            stored = database.get_job(job.job_id)
            self.assertIsNotNone(stored)
            self.assertEqual(stored["status"], "planned")

