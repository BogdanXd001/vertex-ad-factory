from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from vertex_ad_factory.config import Settings
from vertex_ad_factory.services.installation import install_comfyui_dashboard


class InstallationTests(TestCase):
    def test_dashboard_install_is_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            source = project / "comfyui_extension" / "vertex_ad_factory_ui"
            source.mkdir(parents=True)
            comfy = root / "ComfyUI"
            (comfy / "custom_nodes").mkdir(parents=True)
            (comfy / "main.py").touch()
            settings = Settings(
                project_root=project,
                database_path=project / "data" / "database.sqlite3",
                workflows_dir=project / "workflows",
                runs_dir=project / "runs",
                runtime_config_path=project / "data" / "runtime.json",
            )

            first = install_comfyui_dashboard(settings, comfy)
            second = install_comfyui_dashboard(settings, comfy)

            destination = comfy / "custom_nodes" / "vertex_ad_factory_ui"
            self.assertTrue(destination.is_symlink())
            self.assertEqual(destination.resolve(), source.resolve())
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
