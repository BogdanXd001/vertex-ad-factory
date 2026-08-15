import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from vertex_ad_factory.config import Settings
from vertex_ad_factory.orchestrator import Orchestrator
from vertex_ad_factory.services.blueprints import load_blueprint, parse_blueprint


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_PATH = ROOT / "blueprints" / "oceaura_expert_podcast_30s.json"


class BlueprintTests(TestCase):
    def test_oceaura_pilot_is_a_valid_30_70_hybrid(self) -> None:
        blueprint = load_blueprint(BLUEPRINT_PATH)

        self.assertEqual(blueprint.target_duration_seconds, 30)
        self.assertEqual(len(blueprint.scenes), 7)
        self.assertEqual(blueprint.a_roll_seconds, 8)
        self.assertEqual(blueprint.b_roll_seconds, 22)
        self.assertAlmostEqual(blueprint.a_roll_ratio, 8 / 30)
        self.assertEqual(
            [scene.position for scene in blueprint.scenes], list(range(1, 8))
        )

    def test_on_camera_scenes_require_lipsync(self) -> None:
        payload = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
        payload["scenes"][0]["requires_lipsync"] = False

        with self.assertRaisesRegex(ValueError, "must require lip-sync"):
            parse_blueprint(payload)

    def test_total_duration_must_match_blueprint(self) -> None:
        payload = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
        invalid = deepcopy(payload)
        invalid["scenes"][-1]["duration_seconds"] = 6

        with self.assertRaisesRegex(ValueError, "duration total"):
            parse_blueprint(invalid)

    def test_blueprint_creates_job_and_scene_metadata_atomically(self) -> None:
        blueprint = load_blueprint(BLUEPRINT_PATH)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(
                project_root=root,
                database_path=root / "data" / "test.sqlite3",
                workflows_dir=root / "workflows",
                runs_dir=root / "runs",
            )
            orchestrator = Orchestrator(settings)
            job = orchestrator.create_from_blueprint(blueprint)
            scenes = orchestrator.database.list_scenes(job.job_id)

            self.assertEqual(job.status.value, "planned")
            self.assertEqual(len(scenes), 7)
            self.assertEqual(scenes[0]["metadata"]["visual_mode"], "expert_podcast")
            self.assertTrue(scenes[0]["metadata"]["requires_lipsync"])
            self.assertEqual(
                scenes[1]["metadata"]["visual_mode"], "educational_animation"
            )

