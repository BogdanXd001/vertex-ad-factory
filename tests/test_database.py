import sqlite3
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
                    metadata={"visual_mode": "expert_podcast"},
                )
            )
            scene = database.get_scene_by_position(job.job_id, 1)
            self.assertIsNotNone(scene)
            self.assertEqual(scene["metadata"]["visual_mode"], "expert_podcast")
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

    def test_initialize_migrates_existing_scene_table_without_data_loss(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE scenes (
                        scene_id TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        kind TEXT NOT NULL,
                        duration_seconds INTEGER NOT NULL,
                        narration TEXT NOT NULL,
                        visual_prompt TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL,
                        output_json TEXT NOT NULL DEFAULT '{}',
                        error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO scenes VALUES (
                        'scene-1', 'job-1', 1, 'a_roll', 6, 'Legacy narration',
                        'Legacy prompt', 'pending', '{}', NULL, 'now', 'now'
                    );
                    """
                )

            database = Database(path)
            database.initialize()
            with database.connect() as connection:
                row = connection.execute(
                    "SELECT narration, metadata_json FROM scenes WHERE scene_id = 'scene-1'"
                ).fetchone()

            self.assertEqual(row["narration"], "Legacy narration")
            self.assertEqual(row["metadata_json"], "{}")

